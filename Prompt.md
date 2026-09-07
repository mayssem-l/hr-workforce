
Analyse this repo then create three files under the folder /frontend: PLAN.md: here you will outline the goal of the project and you will
dvivide the tasks needed to reach that goal into groups (named milestones). You will also state the architecture and
the technologies used in this file. Then create a CURRENT_TASKS.md where you put in the group of tasks (milestone)
that you are working now, which you will update after finishing each task. Also, create a LESSONS_LEARNED.md where
you keep track of your mistakes and the tips that you discovered that help accelerate the development process. Check
this file regularly and update it whenever applicable (e.g. mistake discovered, tip found, etc.).
  
Here is the description of the project:
"""
We built an **HR workforce planning and team recommendation application in Django**. The goal is to help managers understand employee capacity, project requirements, workload, and staffing options, then recommend suitable project teams in a transparent and explainable way.

So far, most of the work has been focused on the backend and decision-support logic. The main parts are:

* **Django data model** for employees, skills, employee skill levels, projects, project skill requirements, assignments, leave, attendance, and related HR data.
* **Workload and availability services** that calculate how much capacity an employee actually has for a project, taking assignments and approved leave into account.
* **Project matching logic** that scores how well employees fit a project using skills, workload, leave availability, and experience.
* **OR-Tools optimization** that verifies whether a proposed team can cover all mandatory project effort and distributes the required work across qualified employees while respecting capacity constraints.
* **Team metrics** such as project fit, remaining capacity, maximum utilization, workload spread, and team size.
* **Pareto filtering** that reduces the large set of feasible teams to a smaller set of non-dominated alternatives.
* **Recommendation selection** that produces three different staffing strategies, such as a compact team, a balanced alternative, and a higher-capacity alternative.
* **Explainability layer** that generates deterministic strengths and trade-offs for each recommendation.
* **LLM integration with Gemini** that turns those structured facts into short, manager-friendly English summaries without making the staffing decisions itself.

The next stage is to build the **Django interface** around this backend: CRUD screens for the main entities, a workforce dashboard, employee workload and availability views, project planning pages, calendars and visualizations, and a recommendation screen that presents the suggested teams in an intuitive way.
"""

The backend part is almost done and in the next steps (after you finish planning) we will build the frontend (under the folder /frontend) step by step, using the .md files that you will create. don't do anything yet.