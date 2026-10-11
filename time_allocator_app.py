import sqlite3
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

DB_PATH = Path(__file__).resolve().parent / "data" / "planner.db"


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


class PlannerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Time Allocator")
        self.root.geometry("1100x680")
        self.db = PlannerDB()
        self.task_lookup = {}

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

        refresh_btn = ttk.Button(top, text="Refresh", command=self.refresh_all)
        refresh_btn.grid(row=0, column=4, padx=(0, 10))

        action = ttk.Frame(self.planner_tab, padding=(12, 0, 12, 12))
        action.pack(fill="x")

        ttk.Label(action, text="Task:").grid(row=0, column=0, sticky="w")
        self.task_combo = ttk.Combobox(action, state="readonly", width=34)
        self.task_combo.grid(row=0, column=1, padx=(5, 10))

        ttk.Label(action, text="Minutes:").grid(row=0, column=2, sticky="w")
        self.minutes_entry = ttk.Entry(action, width=8)
        self.minutes_entry.insert(0, "30")
        self.minutes_entry.grid(row=0, column=3, padx=(5, 10))

        add_btn = ttk.Button(action, text="Add to plan", command=self.add_selected_task)
        add_btn.grid(row=0, column=4, padx=(0, 10))

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

        create_btn = ttk.Button(form, text="Add task", command=self.add_task)
        create_btn.grid(row=2, column=3, sticky="w", pady=(8, 0))

        list_frame = ttk.LabelFrame(self.tasks_tab, text="Current tasks", padding=12)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tasks_tree = ttk.Treeview(list_frame, columns=("title", "category", "priority", "minutes", "recurrence"), show="headings")
        for column in ("title", "category", "priority", "minutes", "recurrence"):
            self.tasks_tree.heading(column, text=column.replace("_", " ").title())
            self.tasks_tree.column(column, width=160, anchor="center")
        self.tasks_tree.pack(fill="both", expand=True)

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
        total = self.db.get_total_minutes_for_day(day)
        free_time = self.free_time_var.get().strip()
        try:
            free_time_value = int(free_time)
        except ValueError:
            free_time_value = 0

        category_totals = self.db.get_category_totals(day)
        summary = []
        summary.append(f"Date: {day}\n")
        summary.append(f"Allocated: {total} minutes")
        summary.append(f"Free time target: {free_time_value} minutes")
        summary.append(f"Remaining: {max(free_time_value - total, 0)} minutes\n")
        summary.append("Category totals:")
        for row in category_totals:
            summary.append(f"- {row['category_name']}: {row['total_minutes']} minutes")
        if not category_totals:
            summary.append("- No allocations yet")

        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, "\n".join(summary))
        self.summary_text.configure(state="disabled")

    def add_task(self):
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
        recurrence = self.recurrence_box.get().strip()

        self.db.add_task(title, category_name, priority, default_minutes, recurrence)
        self.task_title.delete(0, tk.END)
        self.default_minutes.delete(0, tk.END)
        self.default_minutes.insert(0, "45")
        self.refresh_all()

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
        day = self.date_var.get().strip() or date.today().isoformat()
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
