import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.daily_puzzle import DailyPuzzle
from app.models.student_progress import StudentProgress
from app.learning.services.llm import call_llm

FALLBACK_PUZZLES = [
    {
        "category": "Output Predictor",
        "title": "Python Default Mutable Arguments Trap",
        "prompt": "What will be printed when the following Python code is executed?",
        "code_snippet": "def append_to(element, target_list=[]):\n    target_list.append(element)\n    return target_list\n\nlist1 = append_to(10)\nlist2 = append_to(20)\nprint(list1, list2)",
        "options": [
            "[10] [20]",
            "[10, 20] [10, 20]",
            "[10] [10, 20]",
            "TypeError: mutable default argument"
        ],
        "correct_option_index": 1,
        "explanation": "In Python, default arguments are evaluated only once when the function is defined, NOT each time the function is called. Because `target_list` is a mutable list created at definition time, both `list1` and `list2` point to the exact same list in memory. Therefore, appending 20 modifies the shared list to `[10, 20]`.",
        "hint": "Think about when default parameters are evaluated in Python—during function definition time, or runtime?",
        "xp_reward": 50
    },
    {
        "category": "Spot the Bug",
        "title": "Binary Search Integer Overflow / Midpoint Bug",
        "prompt": "Identify the bug in this classic binary search implementation:",
        "code_snippet": "def binary_search(arr, target):\n    low = 0\n    high = len(arr) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            low = mid\n        else:\n            high = mid - 1\n    return -1",
        "options": [
            "The while condition should be `low < high` instead of `low <= high`",
            "`low = mid` causes an infinite loop when `arr[mid] < target`",
            "The calculation `(low + high) // 2` is invalid in Python",
            "The initial `high = len(arr) - 1` misses the last element"
        ],
        "correct_option_index": 1,
        "explanation": "When `arr[mid] < target`, setting `low = mid` without adding 1 causes the search window to never shrink when `high - low == 1`, resulting in an infinite loop! It must be `low = mid + 1`.",
        "hint": "Trace what happens when there are 2 elements left and the target is the second element.",
        "xp_reward": 50
    },
    {
        "category": "Time Complexity",
        "title": "Nested Loop with Halving Step",
        "prompt": "What is the time complexity of the following algorithm in terms of N?",
        "code_snippet": "def mystery_algorithm(n):\n    count = 0\n    i = n\n    while i > 0:\n        for j in range(n):\n            count += 1\n        i = i // 2\n    return count",
        "options": [
            "O(N)",
            "O(N log N)",
            "O(N^2)",
            "O(log N)"
        ],
        "correct_option_index": 1,
        "explanation": "The outer while-loop divides `i` by 2 at each step, so it executes $O(\\log N)$ times. In each iteration of the outer loop, the inner for-loop runs exactly $N$ times. Multiplying them gives a total time complexity of $O(N \\log N)$.",
        "hint": "The outer loop cuts the number in half each time, while the inner loop always runs from 0 to N.",
        "xp_reward": 50
    },
    {
        "category": "Logic Riddle",
        "title": "Bitwise XOR Magic",
        "prompt": "In an array where every number appears twice EXCEPT for one unique number, which single-pass operation finds the unique number in O(1) space?",
        "code_snippet": "nums = [4, 1, 2, 1, 2]\n# Which bitwise operator cancels out duplicate numbers?\nresult = 0\nfor x in nums:\n    result ^= x\nprint(result) # prints 4",
        "options": [
            "Bitwise AND (&)",
            "Bitwise OR (|)",
            "Bitwise XOR (^)",
            "Bitwise NOT (~)"
        ],
        "correct_option_index": 2,
        "explanation": "XOR has two magical properties: `x ^ x = 0` (any number XORed with itself is 0) and `x ^ 0 = x`. Because XOR is commutative and associative, all duplicate numbers cancel out to 0, leaving only the single unique number!",
        "hint": "Remember: A number XORed with itself is always zero, and XOR with zero preserves the number.",
        "xp_reward": 50
    },
    {
        "category": "Output Predictor",
        "title": "JavaScript Scoping & Event Loop (var vs let)",
        "prompt": "What will be printed when the following JavaScript code runs?",
        "code_snippet": "for (var i = 0; i < 3; i++) {\n    setTimeout(() => console.log(i), 10);\n}",
        "options": [
            "0, 1, 2",
            "3, 3, 3",
            "undefined, undefined, undefined",
            "0, 0, 0"
        ],
        "correct_option_index": 1,
        "explanation": "`var` is function-scoped (not block-scoped). By the time the `setTimeout` callbacks execute from the macro-task queue after 10ms, the for-loop has already completed and `i` equals 3. All 3 closures reference the same variable `i`, printing `3, 3, 3`.",
        "hint": "`var` does not create a new binding for each iteration of the loop, whereas `let` does.",
        "xp_reward": 50
    },
    {
        "category": "Algorithmic Logic",
        "title": "Two Pointers vs Hash Map Lookup",
        "prompt": "For the Two-Sum problem on a SORTED array, which approach achieves optimal O(N) time and O(1) auxiliary space?",
        "code_snippet": "def two_sum_sorted(arr, target):\n    left = 0\n    right = len(arr) - 1\n    while left < right:\n        s = arr[left] + arr[right]\n        if s == target:\n            return (left, right)\n        elif s < target:\n            left += 1\n        else:\n            right -= 1",
        "options": [
            "Brute Force Nested Loops",
            "Hash Map Lookup",
            "Two Pointers from opposite ends",
            "Binary Search on all pairs"
        ],
        "correct_option_index": 2,
        "explanation": "Because the array is already sorted, moving the `left` pointer increases the sum and moving the `right` pointer decreases the sum. This allows solving the problem in a single pass $O(N)$ with zero extra memory $O(1)$ space.",
        "hint": "Since the array is already sorted, you don't need extra space for a hash map if you start from the edges.",
        "xp_reward": 50
    },
    {
        "category": "Spot the Bug",
        "title": "Recursion Base Case Missing",
        "prompt": "What critical flaw exists in this recursive factorial function?",
        "code_snippet": "def factorial(n):\n    if n == 1:\n        return 1\n    return n * factorial(n - 1)\n\nprint(factorial(0))",
        "options": [
            "It fails for `factorial(0)` causing infinite recursion (RecursionError)",
            "Factorial of 1 should return 0",
            "`n - 1` causes an index error",
            "The multiplication order must be `factorial(n - 1) * n`"
        ],
        "correct_option_index": 0,
        "explanation": "Mathematical $0! = 1$. Because the base case only checks `n == 1`, calling `factorial(0)` calls `factorial(-1)`, `factorial(-2)`, etc., resulting in a Python `RecursionError: maximum recursion depth exceeded`.",
        "hint": "Check the mathematical definition of 0 factorial ($0! = 1$).",
        "xp_reward": 50
    }
]

def get_today_date_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_or_create_daily_puzzle(target_date=None):
    """
    Returns today's daily puzzle. If not in the database, generates one or fetches from the curated bank.
    """
    date_str = target_date or get_today_date_str()
    
    puzzle = DailyPuzzle.query.filter_by(puzzle_date=date_str).first()
    if puzzle:
        return puzzle
        
    # Select deterministic fallback based on date hash
    idx = int(hashlib.md5(date_str.encode()).hexdigest(), 16) % len(FALLBACK_PUZZLES)
    fb = FALLBACK_PUZZLES[idx]
    
    new_puzzle = DailyPuzzle(
        puzzle_date=date_str,
        category=fb["category"],
        title=fb["title"],
        prompt=fb["prompt"],
        code_snippet=fb.get("code_snippet"),
        options=fb["options"],
        correct_option_index=fb["correct_option_index"],
        explanation=fb["explanation"],
        hint=fb["hint"],
        xp_reward=fb.get("xp_reward", 50)
    )
    db.session.add(new_puzzle)
    db.session.commit()
    return new_puzzle

def get_streak_tier_info(streak_days):
    """
    Returns flame level, title, multiplier, and theme color based on streak count.
    """
    if streak_days >= 14:
        return {
            "tier": "Inferno Master",
            "multiplier": 1.5,
            "badge": "👑",
            "flameColor": "from-amber-400 via-rose-500 to-purple-600",
            "textColor": "text-purple-400",
            "tag": "1.5x XP Boost"
        }
    elif streak_days >= 7:
        return {
            "tier": "Cosmic Plasma",
            "multiplier": 1.25,
            "badge": "🌟",
            "flameColor": "from-indigo-400 via-purple-500 to-pink-500",
            "textColor": "text-indigo-400",
            "tag": "1.25x XP Boost"
        }
    elif streak_days >= 4:
        return {
            "tier": "Blazing Fire",
            "multiplier": 1.1,
            "badge": "🔥",
            "flameColor": "from-amber-500 via-orange-500 to-rose-500",
            "textColor": "text-orange-400",
            "tag": "1.1x XP Boost"
        }
    elif streak_days >= 1:
        return {
            "tier": "Ember Spark",
            "multiplier": 1.0,
            "badge": "✨",
            "flameColor": "from-yellow-400 to-amber-500",
            "textColor": "text-amber-400",
            "tag": "1.0x XP"
        }
    else:
        return {
            "tier": "Unignited",
            "multiplier": 1.0,
            "badge": "🌱",
            "flameColor": "from-gray-500 to-gray-600",
            "textColor": "text-gray-400",
            "tag": "Start Today!"
        }

def get_user_streak_info(user_id):
    """
    Calculates 7-day activity ring (Mon-Sun), current streak, flame tier info, and puzzle status.
    """
    student_progress = StudentProgress.query.filter_by(user_id=user_id).first()
    today_str = get_today_date_str()
    
    streak_days = student_progress.streak_days if student_progress else 0
    freeze_count = student_progress.streak_freeze_count if student_progress else 1
    puzzles_solved = student_progress.puzzles_solved_count if student_progress else 0
    streak_history = list(student_progress.streak_history or []) if student_progress else []
    last_puzzle_date = student_progress.last_puzzle_date if student_progress else None
    
    is_today_solved = (last_puzzle_date == today_str)
    
    # Calculate 7-Day Activity Ring (Mon-Sun of the current week)
    now = datetime.now(timezone.utc)
    # weekday(): Mon=0, Sun=6
    start_of_week = now - timedelta(days=now.weekday())
    
    week_days = []
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        is_completed = (day_str in streak_history) or (day_str == today_str and is_today_solved)
        is_today = (day_str == today_str)
        is_past = (day_date.date() < now.date())
        
        week_days.append({
            "dayName": day_labels[i],
            "date": day_str,
            "completed": is_completed,
            "isToday": is_today,
            "isPast": is_past
        })
        
    tier_info = get_streak_tier_info(streak_days)
    
    return {
        "streakDays": streak_days,
        "isTodaySolved": is_today_solved,
        "freezeCount": freeze_count,
        "puzzlesSolved": puzzles_solved,
        "tierInfo": tier_info,
        "weekDays": week_days
    }

def verify_puzzle_submission(user_id, selected_index):
    """
    Validates user option submission, updates streak and XP with multiplier, and awards milestone badges.
    """
    today_str = get_today_date_str()
    puzzle = get_or_create_daily_puzzle(today_str)
    
    student_progress = StudentProgress.query.filter_by(user_id=user_id).first()
    if not student_progress:
        student_progress = StudentProgress(user_id=user_id, total_xp=0, streak_days=0, badges=[])
        db.session.add(student_progress)
        db.session.flush()
        
    is_correct = (selected_index == puzzle.correct_option_index)
    
    if not is_correct:
        return {
            "success": True,
            "isCorrect": False,
            "explanation": puzzle.explanation,
            "hint": puzzle.hint
        }
        
    # User was correct!
    already_solved_today = (student_progress.last_puzzle_date == today_str)
    
    unlocked_badges = []
    badges = list(student_progress.badges or [])
    
    # Calculate streak increase if not already solved today
    if not already_solved_today:
        student_progress.last_puzzle_date = today_str
        student_progress.puzzles_solved_count = (student_progress.puzzles_solved_count or 0) + 1
        
        history = list(student_progress.streak_history or [])
        if today_str not in history:
            history.append(today_str)
            student_progress.streak_history = history
            
        # Check consecutive days
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        if yesterday_str in history or student_progress.streak_days == 0:
            student_progress.streak_days = (student_progress.streak_days or 0) + 1
        else:
            # Check if streak freeze is available
            if (student_progress.streak_freeze_count or 0) > 0:
                student_progress.streak_freeze_count -= 1
                student_progress.streak_days = (student_progress.streak_days or 0) + 1
            else:
                student_progress.streak_days = 1
                
        # Calculate XP with streak multiplier
        tier_info = get_streak_tier_info(student_progress.streak_days)
        base_xp = puzzle.xp_reward or 50
        xp_earned = int(base_xp * tier_info["multiplier"])
        student_progress.total_xp = (student_progress.total_xp or 0) + xp_earned
        
        # Check streak milestone badges
        milestones = [
            (3, "🏅 3-Day Ignition"),
            (7, "🥈 Week Warrior (7 Days)"),
            (14, "🥇 Fortnight Legend (14 Days)"),
            (30, "💎 Monthly Titan (30 Days)")
        ]
        for days_req, badge_name in milestones:
            if student_progress.streak_days >= days_req and badge_name not in badges:
                badges.append(badge_name)
                unlocked_badges.append(badge_name)
                
        # Check puzzle count badges
        puzzle_milestones = [
            (1, "🧩 First Puzzle Solved"),
            (5, "🧩 Puzzle Novice (5 Solved)"),
            (20, "🧠 Master Mind (20 Solved)")
        ]
        for p_count, badge_name in puzzle_milestones:
            if student_progress.puzzles_solved_count >= p_count and badge_name not in badges:
                badges.append(badge_name)
                unlocked_badges.append(badge_name)
                
        student_progress.badges = badges
        db.session.commit()
    else:
        xp_earned = 0
        tier_info = get_streak_tier_info(student_progress.streak_days)
        
    return {
        "success": True,
        "isCorrect": True,
        "alreadySolvedToday": already_solved_today,
        "xpEarned": xp_earned,
        "newTotalXP": student_progress.total_xp,
        "newStreakDays": student_progress.streak_days,
        "streakTier": tier_info["tier"],
        "streakMultiplier": tier_info["multiplier"],
        "unlockedBadges": unlocked_badges,
        "explanation": puzzle.explanation
    }
