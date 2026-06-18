"""
test_data_model.py — Unit test cho data model, KHÔNG cần file .mpp thật.

Dùng mock data để verify logic của ProjectData (task_count, milestone_count,
get_resources_for_task) hoạt động đúng trước khi build các phần phức tạp hơn.
"""

from datetime import datetime

from core.data_model import Assignment, ProjectData, Resource, Task


def make_sample_project() -> ProjectData:
    tasks = [
        Task(id=1, name="Phase 1", start=datetime(2026, 1, 1), finish=datetime(2026, 1, 10),
             duration_hours=80, percent_complete=100, outline_level=0, is_summary=True),
        Task(id=2, name="Design", start=datetime(2026, 1, 1), finish=datetime(2026, 1, 5),
             duration_hours=40, percent_complete=100, outline_level=1),
        Task(id=3, name="Kickoff Milestone", start=datetime(2026, 1, 1), finish=datetime(2026, 1, 1),
             duration_hours=0, percent_complete=100, outline_level=1, is_milestone=True),
    ]
    resources = [
        Resource(id=1, name="Anh Nguyen", type="Work"),
    ]
    assignments = [
        Assignment(task_id=2, resource_id=1, units=100.0),
    ]
    return ProjectData(
        name="Sample Project",
        start_date=datetime(2026, 1, 1),
        finish_date=datetime(2026, 1, 10),
        tasks=tasks,
        resources=resources,
        assignments=assignments,
    )


def test_task_count_excludes_summary():
    project = make_sample_project()
    # 3 tasks total, 1 is summary -> task_count should be 2
    assert project.task_count == 2


def test_milestone_count():
    project = make_sample_project()
    assert project.milestone_count == 1


def test_get_resources_for_task():
    project = make_sample_project()
    resources = project.get_resources_for_task(task_id=2)
    assert len(resources) == 1
    assert resources[0].name == "Anh Nguyen"


def test_get_resources_for_task_with_no_assignment():
    project = make_sample_project()
    resources = project.get_resources_for_task(task_id=3)
    assert resources == []


def test_task_duration_days_conversion():
    task = Task(id=99, name="Test", start=None, finish=None,
                duration_hours=16, percent_complete=0, outline_level=0)
    assert task.duration_days == 2.0
