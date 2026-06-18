"""
mpp_reader.py — Đọc file .mpp bằng MPXJ và chuẩn hoá thành ProjectData.

MPXJ là thư viện Java open source, được wrap qua Python package `mpxj`
(chạy trên JVM thông qua JPype). Cần Java JRE 8+ đã cài trên máy.
"""

import logging
import os
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import jpype
import mpxj

from core.data_model import Assignment, ProjectData, Resource, Task

logger = logging.getLogger(__name__)


class MppReadError(Exception):
    """Lỗi khi đọc file .mpp — dùng để CLI bắt và in thông báo rõ ràng cho người dùng."""
    pass


def check_java_available() -> bool:
    """
    Kiểm tra Java JRE có sẵn trên máy chưa (MPXJ cần JVM để chạy).
    Cố gắng tự động cấu hình JAVA_HOME trên macOS nếu phát hiện OpenJDK của Homebrew.
    """
    if jpype.isJVMStarted():
        return True

    # 1. Tự động set JAVA_HOME trên macOS nếu phát hiện Homebrew OpenJDK
    if "JAVA_HOME" not in os.environ and sys.platform == "darwin":
        brew_openjdk = "/opt/homebrew/opt/openjdk"
        if os.path.exists(brew_openjdk):
            os.environ["JAVA_HOME"] = brew_openjdk

    # 2. Thử kiểm tra qua JPype.getDefaultJVMPath()
    try:
        jvm_path = jpype.getDefaultJVMPath()
        if jvm_path:
            return True
    except Exception:
        pass

    # 3. Kiểm tra bằng cách chạy java command
    try:
        java_cmd = "java"
        if "JAVA_HOME" in os.environ:
            java_cmd = os.path.join(os.environ["JAVA_HOME"], "bin", "java")
        result = subprocess.run(
            [java_cmd, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def _to_python_datetime(java_date) -> Optional[datetime]:
    """Helper: Chuyển đổi Java Date hoặc LocalDateTime sang Python datetime."""
    if java_date is None:
        return None
    if hasattr(java_date, "getTime"):
        return datetime.fromtimestamp(java_date.getTime() / 1000.0)
    try:
        return datetime.fromisoformat(str(java_date))
    except Exception:
        return None


def _safe_float(val, default: float = 0.0) -> float:
    """Chuyển đổi an toàn sang float, trả về default nếu lỗi hoặc None."""
    if val is None:
        return default
    try:
        return float(val)
    except Exception:
        return default


def _safe_str(val) -> str:
    """Chuyển đổi an toàn sang str, trả về '' nếu None."""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("null", "none") else s


def _strip_rtf(text: str) -> str:
    """Strip RTF tags, trả về plain text."""
    if not text:
        return ""
    if text.startswith("{\\rtf"):
        # Xoá tất cả các lệnh RTF
        text = re.sub(r"\{[^}]*\}", "", text)
        text = re.sub(r"\\[a-z]+\d*\s?", "", text)
        text = re.sub(r"[{}\\]", "", text)
    return text.strip()


def read_mpp(file_path: str) -> ProjectData:
    """
    Đọc file .mpp và trả về ProjectData đã chuẩn hoá.

    Args:
        file_path: đường dẫn tới file .mpp

    Returns:
        ProjectData chứa toàn bộ task/resource/assignment đã parse.

    Raises:
        MppReadError: khi file không tồn tại, không đọc được, hoặc Java thiếu.
    """
    path = Path(file_path)
    if not path.exists():
        raise MppReadError(f"File không tồn tại: {file_path}")
    if path.suffix.lower() != ".mpp":
        raise MppReadError(f"File không đúng định dạng .mpp: {file_path}")

    if not check_java_available():
        raise MppReadError(
            "Không tìm thấy Java JRE trên máy. MPXJ cần Java 8+ để chạy.\n"
            "Hướng dẫn cài: https://adoptium.net/ (hoặc chạy 'brew install openjdk' trên macOS)."
        )

    try:
        if not jpype.isJVMStarted():
            jpype.startJVM("-Dlog4j2.loggerContextFactory=org.apache.logging.log4j.simple.SimpleLoggerContextFactory")

        # Import các class Java từ MPXJ sau khi JVM đã khởi chạy thành công
        from org.mpxj.reader import UniversalProjectReader

        reader = UniversalProjectReader()
        project = reader.read(str(path))
        props = project.getProjectProperties()

        # ----------------------------------------------------------------
        # Project metadata
        # ----------------------------------------------------------------
        project_name = _safe_str(props.getProjectTitle()) or _safe_str(props.getName()) or path.stem
        project_start = _to_python_datetime(props.getStartDate())
        project_finish = _to_python_datetime(props.getFinishDate())
        author = _safe_str(props.getAuthor())
        last_saved = _to_python_datetime(props.getLastSaved())
        currency_symbol = _safe_str(props.getCurrencySymbol())
        minutes_per_day = int(props.getMinutesPerDay()) if props.getMinutesPerDay() else 480
        revision = int(props.getRevision()) if props.getRevision() else 0

        cal_name = ""
        try:
            default_cal = props.getDefaultCalendar()
            if default_cal is not None:
                cal_name = _safe_str(default_cal.getName())
        except Exception:
            pass

        # Custom properties
        custom_properties: dict = {}
        try:
            cp = props.getCustomProperties()
            if cp:
                for entry in cp.entrySet():
                    custom_properties[_safe_str(entry.getKey())] = _safe_str(entry.getValue())
        except Exception:
            pass

        # ----------------------------------------------------------------
        # Build resource lookup (id → name) để gán vào task.resource_names
        # ----------------------------------------------------------------
        resource_name_map: dict[int, str] = {}

        # Map các Resource
        resources = []
        for raw_resource in project.getResources():
            if raw_resource.getID() is None or int(raw_resource.getID()) == 0:
                continue
            r = _map_resource(raw_resource)
            resources.append(r)
            resource_name_map[r.id] = r.name

        # ----------------------------------------------------------------
        # Map các Assignment (cần trước để gán resource_names cho task)
        # ----------------------------------------------------------------
        assignments = []
        task_resource_map: dict[int, list[str]] = {}   # task_id → [resource_name, ...]

        for raw_assignment in project.getResourceAssignments():
            t_obj = raw_assignment.getTask()
            r_obj = raw_assignment.getResource()
            if t_obj is not None and r_obj is not None:
                task_id = t_obj.getID()
                resource_id = r_obj.getID()
                if task_id is not None and resource_id is not None:
                    if int(resource_id) == 0:
                        continue
                    assignments.append(_map_assignment(raw_assignment))
                    tid = int(task_id)
                    rname = resource_name_map.get(int(resource_id), "")
                    if rname:
                        task_resource_map.setdefault(tid, []).append(rname)

        # ----------------------------------------------------------------
        # Map các Task
        # ----------------------------------------------------------------
        tasks = []
        for raw_task in project.getTasks():
            if raw_task.getID() is None:
                continue
            t = _map_task(raw_task, props)
            t.resource_names = task_resource_map.get(t.id, [])
            tasks.append(t)

        return ProjectData(
            name=str(project_name),
            start_date=project_start,
            finish_date=project_finish,
            tasks=tasks,
            resources=resources,
            assignments=assignments,
            author=author,
            last_saved=last_saved,
            currency_symbol=currency_symbol,
            minutes_per_day=minutes_per_day,
            calendar_name=cal_name,
            revision=revision,
            custom_properties=custom_properties,
        )

    except Exception as exc:
        logger.exception("Lỗi khi đọc file .mpp: %s", file_path)
        raise MppReadError(
            f"Không thể đọc file .mpp. File có thể bị hỏng hoặc có mật khẩu. Chi tiết: {exc}"
        ) from exc


def _map_task(raw_task, props) -> Task:
    """Helper: convert 1 object Task của MPXJ sang dataclass Task nội bộ."""
    from org.mpxj import TimeUnit

    task_id = int(raw_task.getID())
    name = _safe_str(raw_task.getName())
    start = _to_python_datetime(raw_task.getStart())
    finish = _to_python_datetime(raw_task.getFinish())

    # Duration (giờ)
    duration_hours = 0.0
    duration = raw_task.getDuration()
    if duration is not None:
        try:
            converted_duration = duration.convertUnits(TimeUnit.HOURS, props)
            duration_hours = float(converted_duration.getDuration())
        except Exception:
            duration_hours = float(duration.getDuration())
            if str(duration.getUnits()) == "DAYS":
                duration_hours *= 8.0

    percent_complete = _safe_float(raw_task.getPercentageComplete())
    outline_level = int(raw_task.getOutlineLevel()) if raw_task.getOutlineLevel() is not None else 0
    is_milestone = bool(raw_task.getMilestone()) if raw_task.getMilestone() is not None else False
    is_summary = bool(raw_task.getSummary()) if raw_task.getSummary() is not None else False

    # Predecessors
    predecessors = []
    try:
        for relation in raw_task.getPredecessors():
            pred_task = relation.getPredecessorTask()
            if pred_task is not None and pred_task.getID() is not None:
                predecessors.append(int(pred_task.getID()))
    except Exception:
        pass

    # --- Fields mở rộng ---
    wbs = _safe_str(raw_task.getWBS())

    priority = 500
    try:
        p = raw_task.getPriority()
        if p is not None:
            priority = int(p.getValue())
    except Exception:
        pass

    cost = _safe_float(raw_task.getCost())
    actual_cost = _safe_float(raw_task.getActualCost())

    constraint_type = ""
    try:
        ct = raw_task.getConstraintType()
        if ct is not None:
            constraint_type = _safe_str(ct)
    except Exception:
        pass

    is_critical = False
    try:
        c = raw_task.getCritical()
        if c is not None:
            is_critical = bool(c)
    except Exception:
        pass

    # Slack (convert sang ngày)
    free_slack_days = 0.0
    total_slack_days = 0.0
    try:
        fs = raw_task.getFreeSlack()
        if fs is not None:
            fsc = fs.convertUnits(TimeUnit.HOURS, props)
            free_slack_days = round(float(fsc.getDuration()) / 8.0, 2)
    except Exception:
        pass
    try:
        ts = raw_task.getTotalSlack()
        if ts is not None:
            tsc = ts.convertUnits(TimeUnit.HOURS, props)
            total_slack_days = round(float(tsc.getDuration()) / 8.0, 2)
    except Exception:
        pass

    # Notes
    notes = ""
    try:
        n = raw_task.getNotes()
        if n:
            notes = _strip_rtf(str(n))
    except Exception:
        pass

    return Task(
        id=task_id,
        name=name,
        start=start,
        finish=finish,
        duration_hours=duration_hours,
        percent_complete=percent_complete,
        outline_level=outline_level,
        predecessors=predecessors,
        is_milestone=is_milestone,
        is_summary=is_summary,
        wbs=wbs,
        priority=priority,
        cost=cost,
        actual_cost=actual_cost,
        constraint_type=constraint_type,
        is_critical=is_critical,
        free_slack_days=free_slack_days,
        total_slack_days=total_slack_days,
        notes=notes,
    )


def _map_resource(raw_resource) -> Resource:
    """Convert 1 object Resource của MPXJ sang dataclass Resource."""
    res_id = int(raw_resource.getID())
    name = _safe_str(raw_resource.getName())

    raw_type = _safe_str(raw_resource.getType()) if raw_resource.getType() is not None else "WORK"
    if "material" in raw_type.lower():
        res_type = "Material"
    elif "cost" in raw_type.lower():
        res_type = "Cost"
    else:
        res_type = "Work"

    initials = _safe_str(raw_resource.getInitials())
    email = _safe_str(raw_resource.getEmailAddress()) if hasattr(raw_resource, "getEmailAddress") else ""
    max_units = _safe_float(raw_resource.getMaxUnits(), 100.0)

    std_rate = ""
    try:
        rate = raw_resource.getStandardRate()
        if rate is not None:
            std_rate = _safe_str(rate)
    except Exception:
        pass

    cal_name = ""
    try:
        cal = raw_resource.getCalendar()
        if cal is not None:
            cal_name = _safe_str(cal.getName())
    except Exception:
        pass

    notes = ""
    try:
        n = raw_resource.getNotes()
        if n:
            notes = _strip_rtf(str(n))
    except Exception:
        pass

    return Resource(
        id=res_id,
        name=name,
        type=res_type,
        initials=initials,
        email=email,
        max_units=max_units,
        std_rate=std_rate,
        calendar_name=cal_name,
        notes=notes,
    )


def _map_assignment(raw_assignment) -> Assignment:
    """Convert 1 object ResourceAssignment của MPXJ sang dataclass Assignment."""
    task_id = int(raw_assignment.getTask().getID())
    resource_id = int(raw_assignment.getResource().getID())

    units = _safe_float(raw_assignment.getUnits(), 100.0)
    cost = _safe_float(raw_assignment.getCost())
    actual_cost = _safe_float(raw_assignment.getActualCost())

    work_hours = 0.0
    actual_work_hours = 0.0
    try:
        w = raw_assignment.getWork()
        if w is not None:
            work_hours = _safe_float(w.getDuration())
    except Exception:
        pass
    try:
        aw = raw_assignment.getActualWork()
        if aw is not None:
            actual_work_hours = _safe_float(aw.getDuration())
    except Exception:
        pass

    return Assignment(
        task_id=task_id,
        resource_id=resource_id,
        units=units,
        work_hours=work_hours,
        actual_work_hours=actual_work_hours,
        cost=cost,
        actual_cost=actual_cost,
    )
