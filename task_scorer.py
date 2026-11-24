import datetime

PRIORITY_WEIGHTS = {
    "urgent": 40,
    "high": 30,
    "normal": 20,
    "medium": 20,  # alias for backward compatibility
    "low": 10
}

def calculate_task_score(task, today_date=None):
    """
    PRD 7장 자동 정렬 규칙:
    score = priorityWeight(긴급 40, 높음 30, 보통 20, 낮음 10)
          + (마감 지남 +30 | 오늘 +20 | 3일 이내 +10)
          + (예상 시간 <= 30분이면 +2)
    완료 항목은 항상 아래.
    """
    if task.get("done", False):
        return -1000  # Done tasks sorted to the bottom

    if today_date is None:
        today_date = datetime.date.today()

    score = 0

    # 1. Priority weight
    priority = (task.get("priority") or "normal").lower()
    score += PRIORITY_WEIGHTS.get(priority, 20)

    # 2. Due date score
    due_date_str = task.get("dueDate") or task.get("due_date")
    if due_date_str:
        try:
            due_date = datetime.date.fromisoformat(due_date_str)
            days_diff = (due_date - today_date).days
            if days_diff < 0:
                score += 30  # Overdue
            elif days_diff == 0:
                score += 20  # Due today
            elif days_diff <= 3:
                score += 10  # Due within 3 days
        except (ValueError, TypeError):
            pass

    # 3. Quick task bonus
    estimate_min = task.get("estimateMin") or task.get("estimate_min") or 0
    if 0 < estimate_min <= 30:
        score += 2

    return score


def sort_tasks(tasks, today_date=None):
    """
    Sorts tasks by calculated score (descending), then by order, then by creation date.
    Done tasks are pushed to the bottom.
    """
    if today_date is None:
        today_date = datetime.date.today()

    def sort_key(t):
        done_flag = 1 if t.get("done", False) else 0
        score = calculate_task_score(t, today_date)
        order = t.get("order", 0)
        created_at = t.get("createdAt") or t.get("created_at") or ""
        # Note: we want done_flag=0 first, then highest score, then order, then created_at
        return (done_flag, -score, order, created_at)

    return sorted(tasks, key=sort_key)


def auto_carryover_tasks(tasks, today_date_str=None):
    """
    PRD A2 요구사항:
    앱 시작 시와 자정 이후 첫 접근 시 자동 이월.
    미완료 상태이고 날짜가 오늘 이전인 작업을 오늘 날짜로 업데이트하고 carriedCount를 증가시킴.
    Returns: (updated_tasks, carried_count)
    """
    if today_date_str is None:
        today_date_str = datetime.date.today().isoformat()

    carried_count = 0
    for t in tasks:
        # Check if incomplete and from a past date
        task_date = t.get("date")
        if not t.get("done", False) and task_date and task_date < today_date_str:
            t["date"] = today_date_str
            t["carriedCount"] = t.get("carriedCount", 0) + 1
            t["carried_count"] = t["carriedCount"]
            t["updatedAt"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            carried_count += 1

    return tasks, carried_count
