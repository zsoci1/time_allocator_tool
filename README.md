# Time Allocator Tool

A lightweight desktop planner for organizing free time into meaningful work blocks. The app centers on a simple daily workflow: choose a task, assign minutes, and keep recurring obligations visible.

## Features

- Daily planner for free-time allocation
- Categories and priorities for tasks
- Recurring task tracking
- Missed recurring-task backlog
- Simple stats for the selected day
- SQLite-backed storage for local persistence

## Run it

```bash
python -m pip install -r requirements.txt
python time_allocator_app.py
```

The app stores data in the `data/` folder as `planner.db`.

## Notes

This version is intentionally focused on a fast, manual planning experience. It uses PyQt6 for the desktop GUI, keeps the first release simple, and avoids automatic scheduling or complex analytics.
