import sqlite3
import sys
from datetime import date

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

from planner_data import PlannerDB


class PlannerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Time Allocator")
        self.resize(1100, 720)
        self.db = PlannerDB()
        self.selected_task_id = None
        self.selected_category_id = None
        self.task_lookup = {}

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.build_planner_tab()
        self.build_tasks_tab()
        self.build_stats_tab()
        self.refresh_all()

    def build_planner_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top = QHBoxLayout()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(lambda _date: self.refresh_all())
        self.free_time = QSpinBox()
        self.free_time.setRange(0, 1440)
        self.free_time.setValue(120)
        self.free_time.valueChanged.connect(self.update_availability)
        self.remaining_label = QLabel()
        self.remaining_label.setStyleSheet("font-weight: bold;")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_all)
        top.addWidget(QLabel("Date:"))
        top.addWidget(self.date_edit)
        top.addWidget(QLabel("Free time (minutes):"))
        top.addWidget(self.free_time)
        top.addWidget(refresh)
        top.addWidget(self.remaining_label)
        top.addStretch()
        layout.addLayout(top)

        action = QHBoxLayout()
        self.plan_task = QComboBox()
        self.plan_minutes = QSpinBox()
        self.plan_minutes.setRange(1, 1440)
        self.plan_minutes.setValue(30)
        self.add_button = QPushButton("Add to plan")
        self.add_button.clicked.connect(self.add_selected_task)
        done_button = QPushButton("Mark done")
        done_button.clicked.connect(self.mark_selected_done)
        action.addWidget(QLabel("Task:"))
        action.addWidget(self.plan_task, 1)
        action.addWidget(QLabel("Minutes:"))
        action.addWidget(self.plan_minutes)
        action.addWidget(self.add_button)
        action.addWidget(done_button)
        layout.addLayout(action)

        self.plan_table = QTableWidget(0, 5)
        self.plan_table.setHorizontalHeaderLabels(
            ["Task", "Category", "Priority", "Minutes", "Status"]
        )
        self.plan_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.plan_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.plan_table)

        remove = QPushButton("Remove selected block")
        remove.clicked.connect(self.remove_selected_block)
        layout.addWidget(remove)
        self.tabs.addTab(tab, "Daily Planner")

    def build_tasks_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        task_group = QGroupBox("Create or edit task")
        task_form = QFormLayout(task_group)
        self.task_title = QLineEdit()
        self.task_category = QComboBox()
        self.task_priority = QComboBox()
        self.task_priority.addItems(["Low", "Normal", "High"])
        self.task_minutes = QSpinBox()
        self.task_minutes.setRange(1, 1440)
        self.task_minutes.setValue(45)
        self.task_recurrence = QComboBox()
        self.task_recurrence.addItems(["one_time", "daily", "weekly", "monthly"])
        task_form.addRow("Title", self.task_title)
        task_form.addRow("Category", self.task_category)
        task_form.addRow("Priority", self.task_priority)
        task_form.addRow("Default minutes", self.task_minutes)
        task_form.addRow("Recurrence", self.task_recurrence)
        task_buttons = QHBoxLayout()
        self.save_task_button = QPushButton("Add task")
        self.save_task_button.clicked.connect(self.save_task)
        self.delete_task_button = QPushButton("Delete selected")
        self.delete_task_button.setEnabled(False)
        self.delete_task_button.clicked.connect(self.delete_selected_task)
        clear_task = QPushButton("Clear")
        clear_task.clicked.connect(self.clear_task_form)
        task_buttons.addWidget(self.save_task_button)
        task_buttons.addWidget(self.delete_task_button)
        task_buttons.addWidget(clear_task)
        task_form.addRow(task_buttons)
        layout.addWidget(task_group)

        self.tasks_table = QTableWidget(0, 5)
        self.tasks_table.setHorizontalHeaderLabels(
            ["Title", "Category", "Priority", "Minutes", "Recurrence"]
        )
        self.tasks_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tasks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tasks_table.setMinimumHeight(260)
        self.tasks_table.itemSelectionChanged.connect(self.on_task_select)
        layout.addWidget(self.tasks_table)

        category_group = QGroupBox("Create or edit category")
        category_form = QFormLayout(category_group)
        self.category_name = QLineEdit()
        self.category_color = QLineEdit("#4f46e5")
        category_form.addRow("Name", self.category_name)
        category_form.addRow("Color", self.category_color)
        category_buttons = QHBoxLayout()
        self.save_category_button = QPushButton("Add category")
        self.save_category_button.clicked.connect(self.save_category)
        self.delete_category_button = QPushButton("Delete selected")
        self.delete_category_button.setEnabled(False)
        self.delete_category_button.clicked.connect(self.delete_selected_category)
        clear_category = QPushButton("Clear")
        clear_category.clicked.connect(self.clear_category_form)
        category_buttons.addWidget(self.save_category_button)
        category_buttons.addWidget(self.delete_category_button)
        category_buttons.addWidget(clear_category)
        category_form.addRow(category_buttons)
        layout.addWidget(category_group)

        self.categories_table = QTableWidget(0, 3)
        self.categories_table.setHorizontalHeaderLabels(["Name", "Color", "Tasks"])
        self.categories_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.categories_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.categories_table.setMinimumHeight(160)
        self.categories_table.itemSelectionChanged.connect(self.on_category_select)
        layout.addWidget(self.categories_table)

        recurring_group = QGroupBox("Recurring backlog")
        recurring_layout = QVBoxLayout(recurring_group)
        self.recurring_text = QTextEdit()
        self.recurring_text.setReadOnly(True)
        recurring_layout.addWidget(self.recurring_text)
        layout.addWidget(recurring_group)
        self.tabs.addTab(tab, "Tasks")

    def build_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)
        self.tabs.addTab(tab, "Stats")

    def current_day(self):
        return self.date_edit.date().toString("yyyy-MM-dd")

    def refresh_all(self):
        self.refresh_categories()
        self.refresh_tasks()
        self.refresh_plan()
        self.refresh_stats()

    def refresh_categories(self):
        categories = self.db.get_categories()
        self.task_category.clear()
        self.task_category.addItems([item["name"] for item in categories])
        self.categories_table.setRowCount(0)
        tasks = self.db.get_tasks()
        for category in categories:
            row = self.categories_table.rowCount()
            self.categories_table.insertRow(row)
            values = (
                category["name"],
                category["color"],
                str(sum(t["category_id"] == category["id"] for t in tasks)),
            )
            for column, value in enumerate(values):
                self.categories_table.setItem(row, column, QTableWidgetItem(value))
            self.apply_category_color(
                self.categories_table.item(row, 0), category["color"]
            )
            self.categories_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, category["id"]
            )

    def refresh_tasks(self):
        tasks = self.db.get_tasks()
        self.task_lookup = {task["title"]: task["id"] for task in tasks}
        self.plan_task.clear()
        self.plan_task.addItems([task["title"] for task in tasks])
        self.tasks_table.setRowCount(0)
        for task in tasks:
            row = self.tasks_table.rowCount()
            self.tasks_table.insertRow(row)
            values = (
                task["title"],
                task["category_name"],
                task["priority"],
                str(task["default_minutes"]),
                task["recurrence"],
            )
            for column, value in enumerate(values):
                self.tasks_table.setItem(row, column, QTableWidgetItem(value))
            self.apply_category_color(
                self.tasks_table.item(row, 1), task["category_color"]
            )
            self.tasks_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, task["id"]
            )

        missed = self.db.get_missed_recurring_tasks()
        self.recurring_text.setPlainText(
            "No missed recurring tasks."
            if not missed
            else "\n".join(
                f"- {item['title']} ({item['category_name']}): {item['status']}"
                for item in missed
            )
        )

    def refresh_plan(self):
        records = self.db.get_plan_for_day(self.current_day())
        self.plan_table.setRowCount(0)
        for item in records:
            row = self.plan_table.rowCount()
            self.plan_table.insertRow(row)
            values = (
                item["title"],
                item["category_name"],
                item["priority"],
                str(item["minutes"]),
                "Done" if item["completed"] else "Planned",
            )
            for column, value in enumerate(values):
                self.plan_table.setItem(row, column, QTableWidgetItem(value))
            self.apply_category_color(
                self.plan_table.item(row, 1), item["category_color"]
            )
            self.plan_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, item["id"]
            )
        self.update_availability()

    @staticmethod
    def apply_category_color(item, color):
        background = QColor(color)
        if not background.isValid():
            return
        item.setBackground(background)
        luminance = (
            (0.299 * background.red())
            + (0.587 * background.green())
            + (0.114 * background.blue())
        )
        item.setForeground(QColor("#000000" if luminance > 150 else "#ffffff"))

    def refresh_stats(self):
        day = self.current_day()
        completed = self.db.get_completed_total_minutes_for_day(day)
        categories = self.db.get_completed_category_totals(day)
        lines = [
            f"Date: {day}",
            f"Completed: {completed} minutes",
            f"Free time target: {self.free_time.value()} minutes",
            f"Uncompleted: {max(self.free_time.value() - completed, 0)} minutes",
            "",
            "Category totals:",
        ]
        lines.extend(
            f"- {item['category_name']}: {item['total_minutes']} minutes"
            for item in categories
        )
        if not categories:
            lines.append("- No completed tasks yet")
        self.stats_text.setPlainText("\n".join(lines))

    def update_availability(self):
        allocated = self.db.get_total_minutes_for_day(self.current_day())
        remaining = self.free_time.value() - allocated
        if remaining < 0:
            self.remaining_label.setText(f"Over capacity by {abs(remaining)} min")
        else:
            self.remaining_label.setText(f"Remaining: {remaining} min")
        self.add_button.setEnabled(remaining > 0)
        self.refresh_stats()

    def add_selected_task(self):
        task_id = self.task_lookup.get(self.plan_task.currentText())
        if task_id is None:
            QMessageBox.warning(self, "No task selected", "Pick a task first.")
            return
        allocated = self.db.get_total_minutes_for_day(self.current_day())
        remaining = self.free_time.value() - allocated
        if self.plan_minutes.value() > remaining:
            QMessageBox.warning(
                self,
                "Free time limit reached",
                f"Only {max(remaining, 0)} minutes remain.",
            )
            return
        self.db.add_allocation(task_id, self.current_day(), self.plan_minutes.value())
        self.refresh_all()

    def selected_id(self, table):
        items = table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def mark_selected_done(self):
        allocation_id = self.selected_id(self.plan_table)
        if allocation_id is None:
            QMessageBox.information(self, "No selection", "Select a planned task first.")
            return
        self.db.mark_allocation_done(int(allocation_id))
        self.refresh_all()

    def remove_selected_block(self):
        allocation_id = self.selected_id(self.plan_table)
        if allocation_id is None:
            QMessageBox.information(self, "No selection", "Select a planned task first.")
            return
        self.db.remove_allocation(int(allocation_id))
        self.refresh_all()

    def save_task(self):
        title = self.task_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Missing title", "Enter a task title.")
            return
        try:
            if self.selected_task_id is None:
                self.db.add_task(
                    title,
                    self.task_category.currentText(),
                    self.task_priority.currentText(),
                    self.task_minutes.value(),
                    self.task_recurrence.currentText(),
                )
            else:
                self.db.update_task(
                    self.selected_task_id,
                    title,
                    self.task_category.currentText(),
                    self.task_priority.currentText(),
                    self.task_minutes.value(),
                    self.task_recurrence.currentText(),
                )
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate task", "That task already exists.")
            return
        self.clear_task_form()
        self.refresh_all()

    def on_task_select(self):
        task_id = self.selected_id(self.tasks_table)
        if task_id is None:
            return
        task = next(t for t in self.db.get_tasks() if t["id"] == task_id)
        self.selected_task_id = task_id
        self.task_title.setText(task["title"])
        self.task_category.setCurrentText(task["category_name"])
        self.task_priority.setCurrentText(task["priority"])
        self.task_minutes.setValue(task["default_minutes"])
        self.task_recurrence.setCurrentText(task["recurrence"])
        self.save_task_button.setText("Save changes")
        self.delete_task_button.setEnabled(True)

    def clear_task_form(self):
        self.selected_task_id = None
        self.task_title.clear()
        self.task_priority.setCurrentText("Normal")
        self.task_minutes.setValue(45)
        self.task_recurrence.setCurrentText("one_time")
        self.save_task_button.setText("Add task")
        self.delete_task_button.setEnabled(False)

    def delete_selected_task(self):
        if self.selected_task_id is None:
            return
        if QMessageBox.question(self, "Delete task", "Delete this task and allocations?") != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_task(self.selected_task_id)
        self.clear_task_form()
        self.refresh_all()

    def save_category(self):
        name = self.category_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter a category name.")
            return
        try:
            if self.selected_category_id is None:
                self.db.add_category(name, self.category_color.text().strip() or "#4f46e5")
            else:
                self.db.update_category(
                    self.selected_category_id,
                    name,
                    self.category_color.text().strip() or "#4f46e5",
                )
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate category", "That category already exists.")
            return
        self.clear_category_form()
        self.refresh_all()

    def on_category_select(self):
        category_id = self.selected_id(self.categories_table)
        if category_id is None:
            return
        category = next(c for c in self.db.get_categories() if c["id"] == category_id)
        self.selected_category_id = category_id
        self.category_name.setText(category["name"])
        self.category_color.setText(category["color"])
        self.save_category_button.setText("Save changes")
        self.delete_category_button.setEnabled(True)

    def clear_category_form(self):
        self.selected_category_id = None
        self.category_name.clear()
        self.category_color.setText("#4f46e5")
        self.save_category_button.setText("Add category")
        self.delete_category_button.setEnabled(False)

    def delete_selected_category(self):
        if self.selected_category_id is None:
            return
        if QMessageBox.question(self, "Delete category", "Delete this category?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.delete_category(self.selected_category_id)
        except ValueError as error:
            QMessageBox.warning(self, "Unable to delete category", str(error))
            return
        self.clear_category_form()
        self.refresh_all()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PlannerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
