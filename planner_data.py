import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
DB_PATH = APP_DIR / "data" / "planner.db"


class PlannerDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#4f46e5'
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Normal',
                default_minutes INTEGER NOT NULL DEFAULT 30,
                recurrence TEXT NOT NULL DEFAULT 'one_time',
                last_completed_on TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_DATE,
                FOREIGN KEY(category_id) REFERENCES categories(id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_allocations_date ON allocations(date)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category_id)"
        )
        self.conn.execute(
            "DELETE FROM tasks WHERE id NOT IN (SELECT MIN(id) FROM tasks GROUP BY title)"
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_title_unique ON tasks(title)"
        )
        self.conn.commit()
        self.seed_data()

    def seed_data(self):
        category_names = [
            ("Deep Work", "#6366f1"),
            ("Admin", "#f59e0b"),
            ("Health", "#10b981"),
            ("Home", "#ec4899"),
        ]
        for name, color in category_names:
            self.conn.execute(
                "INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)",
                (name, color),
            )

        tasks = [
            ("Deep writing sprint", "Deep Work", "High", 90, "one_time"),
            ("Inbox cleanup", "Admin", "Normal", 30, "one_time"),
            ("Workout", "Health", "High", 45, "weekly"),
            ("Aquarium maintenance", "Home", "Normal", 40, "weekly"),
            ("House reset", "Home", "Low", 25, "one_time"),
        ]
        for title, category_name, priority, default_minutes, recurrence in tasks:
            category = self.get_category_by_name(category_name)
            if category is None:
                continue
            self.conn.execute(
                """
                INSERT OR IGNORE INTO tasks (title, category_id, priority, default_minutes, recurrence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, category["id"], priority, default_minutes, recurrence),
            )
        self.conn.commit()

    def get_category_by_name(self, name: str):
        row = self.conn.execute(
            "SELECT * FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def add_category(self, name: str, color: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)",
            (name, color),
        )
        self.conn.commit()

    def update_category(self, category_id: int, name: str, color: str):
        self.conn.execute(
            "UPDATE categories SET name = ?, color = ? WHERE id = ?",
            (name, color, category_id),
        )
        self.conn.commit()

    def delete_category(self, category_id: int):
        task_count = self.conn.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE category_id = ?",
            (category_id,),
        ).fetchone()["count"]
        if task_count:
            raise ValueError("Move or delete the category's tasks before deleting it.")
        self.conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self.conn.commit()

    def add_task(self, title: str, category_name: str, priority: str, default_minutes: int, recurrence: str):
        category = self.get_category_by_name(category_name)
        if category is None:
            self.add_category(category_name, "#4f46e5")
            category = self.get_category_by_name(category_name)
        self.conn.execute(
            """
            INSERT INTO tasks (title, category_id, priority, default_minutes, recurrence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, category["id"], priority, default_minutes, recurrence),
        )
        self.conn.commit()

    def update_task(
        self,
        task_id: int,
        title: str,
        category_name: str,
        priority: str,
        default_minutes: int,
        recurrence: str,
    ):
        category = self.get_category_by_name(category_name)
        if category is None:
            raise ValueError("Select an existing category.")
        self.conn.execute(
            """
            UPDATE tasks
            SET title = ?, category_id = ?, priority = ?,
                default_minutes = ?, recurrence = ?
            WHERE id = ?
            """,
            (title, category["id"], priority, default_minutes, recurrence, task_id),
        )
        self.conn.commit()

    def delete_task(self, task_id: int):
        self.conn.execute("DELETE FROM allocations WHERE task_id = ?", (task_id,))
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()

    def get_categories(self):
        rows = self.conn.execute(
            "SELECT * FROM categories ORDER BY name ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_tasks(self):
        rows = self.conn.execute(
            """
            SELECT t.*, c.name AS category_name, c.color AS category_color
            FROM tasks t
            JOIN categories c ON c.id = t.category_id
            ORDER BY c.name ASC, t.title ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_allocation(self, task_id: int, day: str, minutes: int, note: str = ""):
        if minutes <= 0:
            raise ValueError("Minutes must be greater than zero.")
        self.conn.execute(
            """
            INSERT INTO allocations (task_id, date, minutes, note)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, day, minutes, note),
        )
        self.conn.commit()

    def get_plan_for_day(self, day: str):
        rows = self.conn.execute(
            """
            SELECT a.id, a.task_id, a.date, a.minutes, a.completed, a.note,
                   t.title, t.priority, t.recurrence,
                   c.name AS category_name, c.color AS category_color
            FROM allocations a
            JOIN tasks t ON t.id = a.task_id
            JOIN categories c ON c.id = t.category_id
            WHERE a.date = ?
            ORDER BY a.id ASC
            """,
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_total_minutes_for_day(self, day: str):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) AS total FROM allocations WHERE date = ?",
            (day,),
        ).fetchone()
        return int(row["total"]) if row else 0

    def get_completed_total_minutes_for_day(self, day: str):
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(minutes), 0) AS total
            FROM allocations
            WHERE date = ? AND completed = 1
            """,
            (day,),
        ).fetchone()
        return int(row["total"]) if row else 0

    def remove_allocation(self, allocation_id: int):
        self.conn.execute("DELETE FROM allocations WHERE id = ?", (allocation_id,))
        self.conn.commit()

    def mark_allocation_done(self, allocation_id: int):
        self.conn.execute(
            "UPDATE allocations SET completed = 1 WHERE id = ?", (allocation_id,)
        )
        row = self.conn.execute(
            "SELECT a.task_id, a.date, t.recurrence FROM allocations a JOIN tasks t ON t.id = a.task_id WHERE a.id = ?",
            (allocation_id,),
        ).fetchone()
        if row and row["recurrence"] != "one_time":
            self.conn.execute(
                "UPDATE tasks SET last_completed_on = ? WHERE id = ?",
                (row["date"], row["task_id"]),
            )
        self.conn.commit()

    def get_missed_recurring_tasks(self):
        rows = self.conn.execute(
            """
            SELECT t.id, t.title, t.priority, t.recurrence, t.last_completed_on,
                   c.name AS category_name, c.color AS category_color,
                   t.default_minutes
            FROM tasks t
            JOIN categories c ON c.id = t.category_id
            WHERE t.recurrence != 'one_time'
            ORDER BY t.title ASC
            """
        ).fetchall()

        today = date.today()
        missed = []
        for row in rows:
            last_done = row["last_completed_on"]
            if not last_done:
                missed.append({**dict(row), "status": "Missed or never completed"})
                continue
            last_done_dt = datetime.strptime(last_done, "%Y-%m-%d").date()
            if row["recurrence"] == "weekly":
                if last_done_dt < today - timedelta(days=7):
                    missed.append({**dict(row), "status": "Missed this week"})
            elif row["recurrence"] == "monthly":
                if last_done_dt.month != today.month or last_done_dt.year != today.year:
                    missed.append({**dict(row), "status": "Missed this month"})
            elif row["recurrence"] == "daily":
                if last_done_dt < today:
                    missed.append({**dict(row), "status": "Missed today"})
        return missed

    def get_category_totals(self, day: str):
        rows = self.conn.execute(
            """
            SELECT c.name AS category_name, COALESCE(SUM(a.minutes), 0) AS total_minutes
            FROM categories c
            LEFT JOIN tasks t ON t.category_id = c.id
            LEFT JOIN allocations a ON a.task_id = t.id AND a.date = ?
            GROUP BY c.name
            ORDER BY total_minutes DESC, c.name ASC
            """,
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_completed_category_totals(self, day: str):
        rows = self.conn.execute(
            """
            SELECT c.name AS category_name, COALESCE(SUM(a.minutes), 0) AS total_minutes
            FROM categories c
            LEFT JOIN tasks t ON t.category_id = c.id
            LEFT JOIN allocations a
                ON a.task_id = t.id AND a.date = ? AND a.completed = 1
            GROUP BY c.name
            ORDER BY total_minutes DESC, c.name ASC
            """,
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]


class PlannerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Time Allocator")
        self.root.geometry("1100x680")
        self.db = PlannerDB()
        self.task_lookup = {}
        self.selected_task_id = None
        self.selected_category_id = None

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.planner_tab = ttk.Frame(self.notebook)
        self.tasks_tab = ttk.Frame(self.notebook)
        self.stats_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.planner_tab, text="Daily Planner")
        self.notebook.add(self.tasks_tab, text="Tasks")
        self.notebook.add(self.stats_tab, text="Stats")

        self.build_planner_tab()
        self.build_tasks_tab()
        self.build_stats_tab()
        self.refresh_all()

    def build_planner_tab(self):
        top = ttk.Frame(self.planner_tab, padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="Date:").grid(row=0, column=0, sticky="w")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        self.date_entry = ttk.Entry(top, textvariable=self.date_var, width=16)
        self.date_entry.grid(row=0, column=1, padx=(5, 10))

        ttk.Label(top, text="Free time (minutes):").grid(row=0, column=2, sticky="w")
        self.free_time_var = tk.StringVar(value="120")
        self.free_time_entry = ttk.Entry(top, textvariable=self.free_time_var, width=10)
        self.free_time_entry.grid(row=0, column=3, padx=(5, 10))
        self.free_time_var.trace_add("write", self.on_planning_input_changed)

        refresh_btn = ttk.Button(top, text="Refresh", command=self.refresh_all)
        refresh_btn.grid(row=0, column=4, padx=(0, 10))

        self.remaining_var = tk.StringVar()
        ttk.Label(
            top, textvariable=self.remaining_var, font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=5, padx=(8, 0), sticky="w")

        action = ttk.Frame(self.planner_tab, padding=(12, 0, 12, 12))
        action.pack(fill="x")

        ttk.Label(action, text="Task:").grid(row=0, column=0, sticky="w")
        self.task_combo = ttk.Combobox(action, state="readonly", width=34)
        self.task_combo.grid(row=0, column=1, padx=(5, 10))

        ttk.Label(action, text="Minutes:").grid(row=0, column=2, sticky="w")
        self.minutes_entry = ttk.Entry(action, width=8)
        self.minutes_entry.insert(0, "30")
        self.minutes_entry.grid(row=0, column=3, padx=(5, 10))

        self.add_plan_btn = ttk.Button(
            action, text="Add to plan", command=self.add_selected_task
        )
        self.add_plan_btn.grid(row=0, column=4, padx=(0, 10))
        self.date_var.trace_add("write", self.on_planning_input_changed)

        done_btn = ttk.Button(action, text="Mark done", command=self.mark_selected_done)
        done_btn.grid(row=0, column=5)

        table = ttk.Frame(self.planner_tab)
        table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("task", "category", "priority", "minutes", "status")
        self.plan_tree = ttk.Treeview(table, columns=columns, show="headings")
        for column in columns:
            self.plan_tree.heading(column, text=column.replace("_", " ").title())
            self.plan_tree.column(column, width=150, anchor="center")
        self.plan_tree.pack(fill="both", expand=True)

        self.plan_tree.bind("<<TreeviewSelect>>", self.on_plan_select)

        controls = ttk.Frame(self.planner_tab, padding=(12, 0, 12, 12))
        controls.pack(fill="x")
        remove_btn = ttk.Button(controls, text="Remove selected block", command=self.remove_selected_block)
        remove_btn.pack(anchor="w")

    def build_tasks_tab(self):
        form = ttk.LabelFrame(self.tasks_tab, text="Create task", padding=12)
        form.pack(fill="x", padx=12, pady=12)

        ttk.Label(form, text="Title").grid(row=0, column=0, sticky="w")
        self.task_title = ttk.Entry(form, width=28)
        self.task_title.grid(row=0, column=1, padx=(5, 12), sticky="ew")

        ttk.Label(form, text="Category").grid(row=0, column=2, sticky="w")
        self.category_box = ttk.Combobox(form, state="readonly", width=18)
        self.category_box.grid(row=0, column=3, padx=(5, 12), sticky="ew")

        ttk.Label(form, text="Priority").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.priority_box = ttk.Combobox(form, state="readonly", values=["Low", "Normal", "High"], width=18)
        self.priority_box.set("Normal")
        self.priority_box.grid(row=1, column=1, padx=(5, 12), sticky="ew", pady=(8, 0))

        ttk.Label(form, text="Default minutes").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.default_minutes = ttk.Entry(form, width=8)
        self.default_minutes.insert(0, "45")
        self.default_minutes.grid(row=1, column=3, padx=(5, 12), sticky="w", pady=(8, 0))

        ttk.Label(form, text="Recurrence").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.recurrence_box = ttk.Combobox(form, state="readonly", values=["one_time", "weekly", "monthly", "daily"], width=18)
        self.recurrence_box.set("one_time")
        self.recurrence_box.grid(row=2, column=1, padx=(5, 12), sticky="ew", pady=(8, 0))

        task_buttons = ttk.Frame(form)
        task_buttons.grid(row=2, column=3, sticky="w", pady=(8, 0))
        self.save_task_btn = ttk.Button(task_buttons, text="Add task", command=self.save_task)
        self.save_task_btn.pack(side="left")
        self.delete_task_btn = ttk.Button(
            task_buttons, text="Delete selected", command=self.delete_selected_task,
            state="disabled",
        )
        self.delete_task_btn.pack(side="left", padx=(8, 0))
        ttk.Button(task_buttons, text="Clear", command=self.clear_task_form).pack(
            side="left", padx=(8, 0)
        )

        list_frame = ttk.LabelFrame(self.tasks_tab, text="Current tasks", padding=12)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tasks_tree = ttk.Treeview(list_frame, columns=("title", "category", "priority", "minutes", "recurrence"), show="headings")
        for column in ("title", "category", "priority", "minutes", "recurrence"):
            self.tasks_tree.heading(column, text=column.replace("_", " ").title())
            self.tasks_tree.column(column, width=160, anchor="center")
        self.tasks_tree.pack(fill="both", expand=True)
        self.tasks_tree.bind("<<TreeviewSelect>>", self.on_task_select)

        category_form = ttk.LabelFrame(self.tasks_tab, text="Create or edit category", padding=12)
        category_form.pack(fill="x", padx=12, pady=(0, 12))

        ttk.Label(category_form, text="Name").grid(row=0, column=0, sticky="w")
        self.category_name = ttk.Entry(category_form, width=24)
        self.category_name.grid(row=0, column=1, padx=(5, 12))

        ttk.Label(category_form, text="Color").grid(row=0, column=2, sticky="w")
        self.category_color = ttk.Entry(category_form, width=12)
        self.category_color.insert(0, "#4f46e5")
        self.category_color.grid(row=0, column=3, padx=(5, 12))

        category_buttons = ttk.Frame(category_form)
        category_buttons.grid(row=0, column=4, sticky="w")
        self.save_category_btn = ttk.Button(
            category_buttons, text="Add category", command=self.save_category
        )
        self.save_category_btn.pack(side="left")
        self.delete_category_btn = ttk.Button(
            category_buttons, text="Delete selected", command=self.delete_selected_category,
            state="disabled",
        )
        self.delete_category_btn.pack(side="left", padx=(8, 0))
        ttk.Button(category_buttons, text="Clear", command=self.clear_category_form).pack(
            side="left", padx=(8, 0)
        )

        category_list = ttk.LabelFrame(self.tasks_tab, text="Categories", padding=12)
        category_list.pack(fill="x", padx=12, pady=(0, 12))
        self.categories_tree = ttk.Treeview(
            category_list, columns=("name", "color", "task_count"), show="headings", height=5
        )
        for column in ("name", "color", "task_count"):
            self.categories_tree.heading(column, text=column.replace("_", " ").title())
            self.categories_tree.column(column, width=180, anchor="center")
        self.categories_tree.pack(fill="x")
        self.categories_tree.bind("<<TreeviewSelect>>", self.on_category_select)

        recurring_frame = ttk.LabelFrame(self.tasks_tab, text="Recurring backlog", padding=12)
        recurring_frame.pack(fill="x", padx=12)
        self.recurring_text = tk.Text(recurring_frame, height=8, wrap="word", state="disabled")
        self.recurring_text.pack(fill="both", expand=True)

    def build_stats_tab(self):
        summary = ttk.LabelFrame(self.stats_tab, text="Today", padding=12)
        summary.pack(fill="x", padx=12, pady=12)

        self.summary_text = tk.Text(summary, height=12, wrap="word", state="disabled")
        self.summary_text.pack(fill="both", expand=True)

    def refresh_all(self):
        self.refresh_categories()
        self.refresh_tasks()
        self.refresh_plan()
        self.refresh_summary()

    def on_planning_input_changed(self, *_args):
        self.update_availability()

    def refresh_categories(self):
        categories = self.db.get_categories()
        names = [item["name"] for item in categories]
        self.category_box["values"] = names
        if names:
            self.category_box.set(names[0])

    def refresh_tasks(self):
        tasks = self.db.get_tasks()
        self.task_lookup = {task["title"]: task["id"] for task in tasks}
        self.task_combo["values"] = [task["title"] for task in tasks]
        if tasks:
            self.task_combo.set(tasks[0]["title"])

        self.tasks_tree.delete(*self.tasks_tree.get_children())
        for task in tasks:
            self.tasks_tree.insert(
                "",
                "end",
                values=(
                    task["title"],
                    task["category_name"],
                    task["priority"],
                    task["default_minutes"],
                    task["recurrence"],
                ),
                iid=str(task["id"]),
            )

        self.categories_tree.delete(*self.categories_tree.get_children())
        for category in self.db.get_categories():
            task_count = sum(task["category_id"] == category["id"] for task in tasks)
            self.categories_tree.insert(
                "",
                "end",
                values=(category["name"], category["color"], task_count),
                iid=str(category["id"]),
            )

        missed = self.db.get_missed_recurring_tasks()
        self.recurring_text.configure(state="normal")
        self.recurring_text.delete("1.0", tk.END)
        if not missed:
            self.recurring_text.insert(tk.END, "No missed recurring tasks.")
        else:
            for item in missed:
                self.recurring_text.insert(
                    tk.END,
                    f"- {item['title']} ({item['category_name']}): {item['status']}\n",
                )
        self.recurring_text.configure(state="disabled")

    def refresh_plan(self):
        day = self.date_var.get().strip() or date.today().isoformat()
        records = self.db.get_plan_for_day(day)
        self.plan_tree.delete(*self.plan_tree.get_children())
        for item in records:
            self.plan_tree.insert(
                "",
                "end",
                values=(
                    item["title"],
                    item["category_name"],
                    item["priority"],
                    item["minutes"],
                    "Done" if item["completed"] else "Planned",
                ),
                iid=f"{item['id']}",
            )

    def refresh_summary(self):
        day = self.date_var.get().strip() or date.today().isoformat()
        total = self.db.get_completed_total_minutes_for_day(day)
        free_time = self.free_time_var.get().strip()
        try:
            free_time_value = int(free_time)
        except ValueError:
            free_time_value = 0

        self.update_availability(total=total, free_time=free_time_value)

        category_totals = self.db.get_completed_category_totals(day)
        summary = []
        summary.append(f"Date: {day}\n")
        summary.append(f"Completed: {total} minutes")
        summary.append(f"Free time target: {free_time_value} minutes")
        summary.append(f"Uncompleted: {max(free_time_value - total, 0)} minutes\n")
        summary.append("Category totals:")
        for row in category_totals:
            summary.append(f"- {row['category_name']}: {row['total_minutes']} minutes")
        if not category_totals:
            summary.append("- No completed tasks yet")

        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, "\n".join(summary))
        self.summary_text.configure(state="disabled")

    def update_availability(self, total=None, free_time=None):
        day = self.date_var.get().strip() or date.today().isoformat()
        if total is None:
            total = self.db.get_total_minutes_for_day(day)
        if free_time is None:
            try:
                free_time = int(self.free_time_var.get().strip())
            except ValueError:
                free_time = 0

        if free_time < 0:
            self.remaining_var.set("Enter a non-negative free-time target")
            self.add_plan_btn.configure(state="disabled")
            return

        remaining = free_time - total
        if remaining < 0:
            self.remaining_var.set(f"Over capacity by {abs(remaining)} min")
            self.add_plan_btn.configure(state="disabled")
        else:
            self.remaining_var.set(f"Remaining: {remaining} min")
            self.add_plan_btn.configure(
                state="normal" if remaining > 0 else "disabled"
            )

    def save_task(self):
        title = self.task_title.get().strip()
        if not title:
            messagebox.showwarning("Missing task title", "Please provide a title.")
            return
        category_name = self.category_box.get().strip()
        priority = self.priority_box.get().strip()
        try:
            default_minutes = int(self.default_minutes.get())
        except ValueError:
            messagebox.showwarning("Invalid minutes", "The default minutes value must be a number.")
            return
        if default_minutes <= 0:
            messagebox.showwarning("Invalid minutes", "Default minutes must be greater than zero.")
            return
        recurrence = self.recurrence_box.get().strip()

        try:
            if self.selected_task_id is None:
                self.db.add_task(title, category_name, priority, default_minutes, recurrence)
            else:
                self.db.update_task(
                    self.selected_task_id,
                    title,
                    category_name,
                    priority,
                    default_minutes,
                    recurrence,
                )
        except sqlite3.IntegrityError:
            messagebox.showwarning("Duplicate task", "A task with that title already exists.")
            return
        except ValueError as error:
            messagebox.showwarning("Unable to save task", str(error))
            return
        self.clear_task_form()
        self.refresh_all()

    def on_task_select(self, _event):
        selection = self.tasks_tree.selection()
        if not selection:
            return
        task_id = int(selection[0])
        task = next((item for item in self.db.get_tasks() if item["id"] == task_id), None)
        if task is None:
            return
        self.selected_task_id = task_id
        self.task_title.delete(0, tk.END)
        self.task_title.insert(0, task["title"])
        self.category_box.set(task["category_name"])
        self.priority_box.set(task["priority"])
        self.default_minutes.delete(0, tk.END)
        self.default_minutes.insert(0, str(task["default_minutes"]))
        self.recurrence_box.set(task["recurrence"])
        self.save_task_btn.configure(text="Save changes")
        self.delete_task_btn.configure(state="normal")

    def delete_selected_task(self):
        if self.selected_task_id is None:
            return
        if not messagebox.askyesno(
            "Delete task", "Delete this task and its planned allocations?"
        ):
            return
        self.db.delete_task(self.selected_task_id)
        self.clear_task_form()
        self.refresh_all()

    def clear_task_form(self):
        self.selected_task_id = None
        self.task_title.delete(0, tk.END)
        values = self.category_box["values"]
        self.category_box.set(values[0] if values else "")
        self.priority_box.set("Normal")
        self.default_minutes.delete(0, tk.END)
        self.default_minutes.insert(0, "45")
        self.recurrence_box.set("one_time")
        self.save_task_btn.configure(text="Add task")
        self.delete_task_btn.configure(state="disabled")

    def save_category(self):
        name = self.category_name.get().strip()
        color = self.category_color.get().strip() or "#4f46e5"
        if not name:
            messagebox.showwarning("Missing category name", "Please provide a category name.")
            return
        try:
            if self.selected_category_id is None:
                self.db.add_category(name, color)
            else:
                self.db.update_category(self.selected_category_id, name, color)
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Duplicate category", "A category with that name already exists."
            )
            return
        self.clear_category_form()
        self.refresh_all()

    def on_category_select(self, _event):
        selection = self.categories_tree.selection()
        if not selection:
            return
        category_id = int(selection[0])
        category = next(
            (item for item in self.db.get_categories() if item["id"] == category_id),
            None,
        )
        if category is None:
            return
        self.selected_category_id = category_id
        self.category_name.delete(0, tk.END)
        self.category_name.insert(0, category["name"])
        self.category_color.delete(0, tk.END)
        self.category_color.insert(0, category["color"])
        self.save_category_btn.configure(text="Save changes")
        self.delete_category_btn.configure(state="normal")

    def delete_selected_category(self):
        if self.selected_category_id is None:
            return
        if not messagebox.askyesno("Delete category", "Delete this category?"):
            return
        try:
            self.db.delete_category(self.selected_category_id)
        except ValueError as error:
            messagebox.showwarning("Unable to delete category", str(error))
            return
        self.clear_category_form()
        self.refresh_all()

    def clear_category_form(self):
        self.selected_category_id = None
        self.category_name.delete(0, tk.END)
        self.category_color.delete(0, tk.END)
        self.category_color.insert(0, "#4f46e5")
        self.save_category_btn.configure(text="Add category")
        self.delete_category_btn.configure(state="disabled")

    def add_selected_task(self):
        task_name = self.task_combo.get().strip()
        if not task_name:
            messagebox.showwarning("No task selected", "Pick a task before allocating time.")
            return
        task_id = self.task_lookup.get(task_name)
        if task_id is None:
            messagebox.showwarning("Missing task", "That task could not be found.")
            return
        try:
            minutes = int(self.minutes_entry.get())
        except ValueError:
            messagebox.showwarning("Invalid minutes", "Please enter a whole number of minutes.")
            return
        if minutes <= 0:
            messagebox.showwarning(
                "Invalid minutes", "Allocated minutes must be greater than zero."
            )
            return
        day = self.date_var.get().strip() or date.today().isoformat()
        try:
            free_time = int(self.free_time_var.get().strip())
        except ValueError:
            messagebox.showwarning(
                "Invalid free time", "Free time must be a non-negative whole number."
            )
            return
        if free_time < 0:
            messagebox.showwarning(
                "Invalid free time", "Free time must be a non-negative whole number."
            )
            return
        allocated = self.db.get_total_minutes_for_day(day)
        remaining = free_time - allocated
        if minutes > remaining:
            messagebox.showwarning(
                "Free time limit reached",
                f"This block needs {minutes} minutes, but only {max(remaining, 0)} minutes remain.",
            )
            self.update_availability(total=allocated, free_time=free_time)
            return
        self.db.add_allocation(task_id, day, minutes)
        self.minutes_entry.delete(0, tk.END)
        self.minutes_entry.insert(0, "30")
        self.refresh_all()

    def on_plan_select(self, _event):
        pass

    def mark_selected_done(self):
        selection = self.plan_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a planned task first.")
            return
        allocation_id = int(selection[0])
        self.db.mark_allocation_done(allocation_id)
        self.refresh_all()

    def remove_selected_block(self):
        selection = self.plan_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a planned task first.")
            return
        allocation_id = int(selection[0])
        self.db.remove_allocation(allocation_id)
        self.refresh_all()

    def run(self):
        self.root.mainloop()


def main():
    app = PlannerApp()
    app.run()


if __name__ == "__main__":
    main()
