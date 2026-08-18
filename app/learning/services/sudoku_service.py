import random
import hashlib
from datetime import datetime, timezone, timedelta
from app.extensions import db
from app.models.student_progress import StudentProgress
from app.learning.services.daily_puzzle_service import get_streak_tier_info, get_user_streak_info, get_today_date_str

def get_grid_dimensions(size):
    if size == 4:
        return 4, 2, 2
    elif size == 6:
        return 6, 2, 3
    else:
        return 9, 3, 3

def is_valid(grid, r, c, num, size, block_r, block_c):
    # Check row
    if num in grid[r]:
        return False
    # Check column
    if num in [grid[i][c] for i in range(size)]:
        return False
    # Check block
    br_start = (r // block_r) * block_r
    bc_start = (c // block_c) * block_c
    for i in range(br_start, br_start + block_r):
        for j in range(bc_start, bc_start + block_c):
            if grid[i][j] == num:
                return False
    return True

def solve_sudoku(grid, size, block_r, block_c):
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                nums = list(range(1, size + 1))
                random.shuffle(nums)
                for num in nums:
                    if is_valid(grid, r, c, num, size, block_r, block_c):
                        grid[r][c] = num
                        if solve_sudoku(grid, size, block_r, block_c):
                            return True
                        grid[r][c] = 0
                return False
    return True

def generate_sudoku_board(size=4, date_seed=None):
    """
    Generates a daily Sudoku board and its solution.
    """
    size, block_r, block_c = get_grid_dimensions(size)
    
    # Use deterministic date seed if provided
    if date_seed:
        seed_int = int(hashlib.md5(f"sudoku-{size}-{date_seed}".encode()).hexdigest(), 16) % 1000000
        random.seed(seed_int)
    
    grid = [[0]*size for _ in range(size)]
    solve_sudoku(grid, size, block_r, block_c)
    solution = [row[:] for row in grid]
    
    # Clues to leave based on grid size
    clue_counts = {
        4: 8,   # 8 given out of 16
        6: 18,  # 18 given out of 36
        9: 34   # 34 given out of 81
    }
    clues = clue_counts.get(size, 8)
    
    cells = [(r, c) for r in range(size) for c in range(size)]
    random.shuffle(cells)
    removed = size * size - clues
    for r, c in cells[:removed]:
        grid[r][c] = 0
        
    # Reset random seed back to system entropy
    random.seed()
    
    return grid, solution

def get_socratic_sudoku_hint(current_board, solution, size=4):
    """
    Finds the best empty cell and constructs a step-by-step deductive Socratic hint.
    """
    size, block_r, block_c = get_grid_dimensions(size)
    
    # Find all empty cells with their valid candidates
    best_cell = None
    min_candidates = 999
    best_candidates = []
    
    for r in range(size):
        for c in range(size):
            if current_board[r][c] == 0:
                # Find which numbers can go here
                candidates = []
                for num in range(1, size + 1):
                    if is_valid(current_board, r, c, num, size, block_r, block_c):
                        candidates.append(num)
                if len(candidates) < min_candidates and len(candidates) > 0:
                    min_candidates = len(candidates)
                    best_cell = (r, c)
                    best_candidates = candidates
                    
    if not best_cell:
        # Fallback to any empty cell matching solution
        for r in range(size):
            for c in range(size):
                if current_board[r][c] == 0:
                    best_cell = (r, c)
                    best_candidates = [solution[r][c]]
                    break
            if best_cell:
                break
                
    if not best_cell:
        return {
            "row": -1,
            "col": -1,
            "val": -1,
            "hint": "The board is completely filled! Click Verify to check your solution."
        }
        
    r, c = best_cell
    correct_val = solution[r][c]
    
    # Calculate what numbers are already in row, col, and block
    row_nums = sorted([x for x in current_board[r] if x != 0])
    col_nums = sorted([current_board[i][c] for i in range(size) if current_board[i][c] != 0])
    
    br_start = (r // block_r) * block_r
    bc_start = (c // block_c) * block_c
    block_nums = sorted([current_board[i][j] for i in range(br_start, br_start + block_r) for j in range(bc_start, bc_start + block_c) if current_board[i][j] != 0])
    
    all_used = sorted(list(set(row_nums + col_nums + block_nums)))
    used_str = ", ".join(str(x) for x in all_used) if all_used else "none"
    
    explanation = f"Look at Row {r + 1}, Column {c + 1}: The numbers {used_str} are already taken in this row/block. By process of elimination, only {correct_val} can logically fit here!"
    
    return {
        "row": r,
        "col": c,
        "val": correct_val,
        "hint": explanation
    }

def verify_sudoku_board(user_id, submitted_board, solution, size=4):
    """
    Verifies user submission, updates daily streak and XP with multiplier, and awards milestone badges.
    """
    size, block_r, block_c = get_grid_dimensions(size)
    
    # Verify correctness
    is_correct = True
    for r in range(size):
        for c in range(size):
            if submitted_board[r][c] != solution[r][c]:
                is_correct = False
                break
        if not is_correct:
            break
            
    if not is_correct:
        return {
            "success": True,
            "isCorrect": False,
            "message": "Some numbers are incorrect or missing. Use Diva Hint for a clue!"
        }
        
    # User solved it correctly!
    today_str = get_today_date_str()
    student_progress = StudentProgress.query.filter_by(user_id=user_id).first()
    if not student_progress:
        student_progress = StudentProgress(user_id=user_id, total_xp=0, streak_days=0, badges=[])
        db.session.add(student_progress)
        db.session.flush()
        
    already_solved_today = (student_progress.last_puzzle_date == today_str)
    unlocked_badges = []
    badges = list(student_progress.badges or [])
    
    xp_rewards = {4: 50, 6: 75, 9: 100}
    base_xp = xp_rewards.get(size, 50)
    
    if not already_solved_today:
        student_progress.last_puzzle_date = today_str
        student_progress.puzzles_solved_count = (student_progress.puzzles_solved_count or 0) + 1
        
        history = list(student_progress.streak_history or [])
        if today_str not in history:
            history.append(today_str)
            student_progress.streak_history = history
            
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        if yesterday_str in history or student_progress.streak_days == 0:
            student_progress.streak_days = (student_progress.streak_days or 0) + 1
        else:
            if (student_progress.streak_freeze_count or 0) > 0:
                student_progress.streak_freeze_count -= 1
                student_progress.streak_days = (student_progress.streak_days or 0) + 1
            else:
                student_progress.streak_days = 1
                
        tier_info = get_streak_tier_info(student_progress.streak_days)
        xp_earned = int(base_xp * tier_info["multiplier"])
        student_progress.total_xp = (student_progress.total_xp or 0) + xp_earned
        
        # Streak Badges
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
                
        # Sudoku Badges
        if "🧩 Sudoku Solver" not in badges:
            badges.append("🧩 Sudoku Solver")
            unlocked_badges.append("🧩 Sudoku Solver")
            
        if size == 9 and "🧠 Sudoku Master (9x9)" not in badges:
            badges.append("🧠 Sudoku Master (9x9)")
            unlocked_badges.append("🧠 Sudoku Master (9x9)")
            
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
        "message": f"🎉 Fantastic! You solved the {size}x{size} Sudoku and boosted your brain agility!"
    }
