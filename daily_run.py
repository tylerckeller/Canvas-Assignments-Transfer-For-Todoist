# -*- coding: utf-8 -*-
import requests
import re
import json
from todoist_api_python.api import TodoistAPI
from requests.auth import HTTPDigestAuth
import datetime

# Loaded configuration files and creates a list of course_ids
config = {}
header = {}
param = {"per_page": "100", "include": "submission"}
course_ids = []
assignments = []
todoist_tasks = []
courses_id_name_dict = {}
todoist_project_dict = {}


def main():
    print(f"  {'#'*52}")
    print(" #     Canvas-Assignments-Transfer-For-Todoist     #")
    print(f"{'#'*52}\n")
    initialize_api()
    print("API INITIALIZED")
    select_courses()
    print(f"Selected {len(course_ids)} courses")
    print("Syncing Canvas Assignments...")
    load_todoist_projects()
    load_assignments()
    load_todoist_tasks()
    create_todoist_projects()
    transfer_assignments_to_todoist()
    print("Done!")


# Function for Yes/No response prompts during setup
def yes_no(question: str) -> bool:
    reply = None
    while reply not in ("y", "n"):
        reply = input(f"{question} (y/n): ").lower()
    return reply == "y"


# Makes sure that the user has their api keys and canvas url in the config.json
def initialize_api():
    global config
    global todoist_api

    try:
        with open("config.json") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        print("File not Found, running Initial Configuration")
        initial_config()

    # create todoist_api object globally
    todoist_api = TodoistAPI(config["todoist_api_key"].strip())
    header.update({"Authorization": f"Bearer {config['canvas_api_key'].strip()}"})


def initial_config():
    print(
        "Your Todoist API key has not been configured. To add an API token, go to your Todoist settings and copy the API token listed under the Integrations Tab. Copy the token and paste below when you are done."
    )
    config["todoist_api_key"] = input(">")
    print(
        "Your Canvas API key has not been configured. To add an API token, go to your Canvas settings and click on New Access Token under Approved Integrations. Copy the token and paste below when you are done."
    )
    config["canvas_api_key"] = input(">")
    defaults = yes_no("Use default options? (enter n for advanced config)")
    if defaults == True:
        config["canvas_api_heading"] = "https://canvas.instructure.com"
        config["todoist_task_priority"] = 1
        config["todoist_task_labels"] = []
        config["sync_null_assignments"] = True
        config["sync_locked_assignments"] = True
        config["sync_no_due_date_assignments"] = True
    if defaults == False:
        custom_url = yes_no("Use default Canvas URL? (https://canvas.instructure.com)")
        if custom_url == True:
            config["canvas_api_heading"] = "https://canvas.instructure.com"
        if custom_url == False:
            print(
                "Enter your custom Canvas URL: (example https://university.instructure.com)"
            )
            config["canvas_api_heading"] = input(">")
        advance_setup = yes_no(
            "Configure Advanced Options (change priority, labels, or sync null/locked assignments?) (enter n for default config)"
        )
        if advance_setup == True:
            print(
                "Specify the task priority (1=Priority 4, 2=Priority 3, 3=Priority 2, 4=Priority 1. (Default Priority 4)"
            )
            config["todoist_task_priority"] = int(input(">"))
            print(
                "Enter any Label names that you would like assigned to the tasks, separated by space)"
            )
            config_input = input(">")
            config["todoist_task_labels"] = config_input.split()
            null_assignments = yes_no("Sync not graded/not submittable assignments?")
            config["sync_null_assignments"] = null_assignments
            locked_assignments = yes_no("Sync locked assignments?")
            config["sync_locked_assignments"] = locked_assignments
            no_due_date_assignments = yes_no("Sync assignments with no due date?")
            config["sync_no_due_date_assignments"] = no_due_date_assignments

        else:
            config["todoist_task_priority"] = 1
            config["todoist_task_labels"] = []
            config["sync_null_assignments"] = True
            config["sync_locked_assignments"] = True
            config["sync_no_due_date_assignments"] = True
    config["courses"] = []
    with open("config.json", "w") as outfile:
        json.dump(config, outfile)


# Allows the user to select the courses that they want to transfer while generating a dictionary
# that has course ids as the keys and their names as the values
def select_courses():
    global config
    response = requests.get(
        f"{config['canvas_api_heading']}/api/v1/courses", headers=header, params=param
    )
    if response.status_code == 401:
        print("Unauthorized; Check API Key")
        exit()

    if config["courses"]:
        use_previous_input = "y"
        print("")
        if use_previous_input == "y" or use_previous_input == "Y":
            course_ids.extend(
                list(map(lambda course_id: int(course_id), config["courses"]))
            )
            for course in response.json():
                courses_id_name_dict[course.get("id", None)] = re.sub(
                    r"[^-a-zA-Z0-9._\s]", "", course.get("name", "")
                )
            return

    # If the user does not choose to use courses selected last time
    for i, course in enumerate(response.json(), start=1):
        courses_id_name_dict[course.get("id", None)] = re.sub(
            r"[^-a-zA-Z0-9._\s]", "", course.get("name", "")
        )
        if course.get("name") is not None:
            print(
                f"{str(i)} ) {courses_id_name_dict[course.get('id', '')]} : {str(course.get('id', ''))}"
            )

    print(
        "\nEnter the courses you would like to add to Todoist by entering the numbers of the items you would like to select. Separate numbers with spaces."
    )
    my_input = input(">")
    input_array = my_input.split()
    course_ids.extend(
        list(
            map(
                lambda item: response.json()[int(item) - 1].get("id", None), input_array
            )
        )
    )

    # write course ids to config.json
    config["courses"] = course_ids
    with open("config.json", "w") as outfile:
        json.dump(config, outfile)


# Iterates over the course_ids list and loads all of the users assignments
# for those classes. Appends assignment objects to assignments list
def load_assignments():
    for course_id in course_ids:
        response = requests.get(
            f"{config['canvas_api_heading']}/api/v1/courses/{str(course_id)}/assignments",
            headers=header,
            params=param,
        )
        if response.status_code == 401:
            print("Unauthorized; Check API Key")
            exit()
        paginated = response.json()
        while "next" in response.links:
            response = requests.get(
                response.links["next"]["url"], headers=header, params=param
            )
            paginated.extend(response.json())
        assignments.extend(paginated)
    print(f"Loaded {len(assignments)} Canvas Assignments")


# Loads all user tasks from Todoist
def load_todoist_tasks():
    tasks = todoist_api.get_tasks()
    todoist_tasks.extend(tasks)
    print(f"Loaded {len(todoist_tasks)} Todoist Tasks")


# Loads all user projects from Todoist
def load_todoist_projects():
    projects = todoist_api.get_projects()
    for project in projects:
        todoist_project_dict[project.name] = project.id
    print(f"Loaded {len(todoist_project_dict)} Todoist Projects")


# Checks to see if the user has a project matching their course names, if there
# is not a new project will be created
def create_todoist_projects():
    for course_id in course_ids:
        if courses_id_name_dict[course_id] not in todoist_project_dict:
            project = todoist_api.add_project(courses_id_name_dict[course_id])
            print(f"Project {courses_id_name_dict[course_id]} created")
            todoist_project_dict[project.name] = project.id
        else:
            print(f"Project {courses_id_name_dict[course_id]} exists")

# Checks to see if the user has a project named Coursework, if not, creates one
# Then, checks if there are sections in Coursework that match the course names,
# if not, makes them
def create_todoist_sections():
    if "Coursework" not in todoist_project_dict:
        project = todoist_api.add_project("Coursework")
        print("Project Coursework created")
        todoist_project_dict[project.name] = project.id
    else:
        print("Project Coursework exists")

    for course_id in course_ids:
        course_name = courses_id_name_dict[course_id]
        if course_name not in todoist_api.get_sections(project_id=todoist_project_dict["Coursework"]):
            section = todoist_api.add_section(name=course_name, project_id=todoist_project_dict["Coursework"])
            print(f"Section {course_name} created in Coursework")
        else:
            print(f"Section {course_name} exists in Coursework")



# Transfers over assignments from canvas over to Todoist, the method Checks
# to make sure the assignment has not already been transferred to prevent overlap
def transfer_assignments_to_todoist():
    new_added = 0
    updated = 0
    already_synced = 0
    ignored_ungraded = 0
    ignored_nodate = 0
    ignored_locked = 0
    submitted = 0
    for assignment in assignments:
        course_name = courses_id_name_dict[assignment["course_id"]]
        project_id = todoist_project_dict[course_name]

        is_added = False
        is_synced = True

        for task in todoist_tasks:
            # print(task.content)
            if (
                task.content == f"[{assignment['name']}]({assignment['html_url']}) Due"
                and task.project_id == project_id
            ):
                is_added = True
                if (
                    assignment["due_at"] is None
                ):  ##Ignore updates if assignment has no due date and already synced
                    break
                if (
                    task.due is None and assignment["due_at"] is not None
                ):  ##Handle case where task does not have due date but assignment does
                    is_synced = False
                    print(
                        f"Updating assignment due date: {course_name}:{assignment['name']} to {str(assignment['due_at'])}"
                    )
                    break
                if (
                    task.due is not None
                ):  # Check for existence of task.due first to prevent error
                    if (
                        assignment["due_at"] != task.due.datetime
                    ):  ## Handle case where assignment and task both have due dates but they are different
                        is_synced = False
                        print(
                            f"Updating assignment due date: {course_name}:{assignment['name']} to {str(assignment['due_at'])}"
                        )
                        break
            if config["sync_null_assignments"] == False:
                if (
                    assignment["submission_types"][0] == "not_graded"
                    or assignment["submission_types"][0] is None
                ):  ##Handle case where assignment is not graded
                    print(
                        f"Ignoring ungraded/non-submittable assignment: {course_name}: {assignment['name']}"
                    )
                    is_added = True
                    ignored_ungraded += 1
                    break
            if (
                assignment["due_at"] is None
                and config["sync_no_due_date_assignments"] == False
            ):  ##Handle case where assignment has no due date
                print(
                    f"Ignoring assignment with no due date: {course_name}: {assignment['name']}"
                )
                ignored_nodate += 1
                is_added = True
                break
            if (
                assignment["unlock_at"] is not None
                and config["sync_locked_assignments"] == False
                and assignment["unlock_at"]
                > (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat()
            ):
                print(
                    f"Ignoring assignment that is not yet unlocked: {course_name}: {assignment['name']}: {assignment['lock_explanation']}"
                )
                is_added = True
                ignored_locked += 1
                break
            if (
                assignment["locked_for_user"] == True
                and assignment["unlock_at"] is None
                and config["sync_locked_assignments"] == False
            ):
                print(
                    f"Ignoring assignment that is locked: {course_name}: {assignment['name']}: {assignment['lock_explanation']}"
                )
                is_added = True
                ignored_locked += 1
                break

        if not is_added:
            if assignment["submission"]["workflow_state"] == "unsubmitted":
                print(f"Adding assignment {course_name}: {assignment['name']}")
                add_new_task(assignment, project_id)
                new_added += 1
            else:
                submitted += 1
        elif not is_synced:
            update_task(assignment, task)
            updated += 1

        if is_synced and is_added:
            already_synced += 1

    print(f"Total Assignments: {len(assignments)}")
    print(f"Total Already Submitted: {submitted}")
    print(f"Total Added to Todoist: {new_added}")
    print(f"Total Updated In Todoist: {updated}")
    print(f"Total Already Synced: {already_synced}")
    print(f"Ungraded and ignored: {ignored_ungraded}")
    print(f"With no due date and Ignored: {ignored_nodate}")
    print(f"Locked Assignments Ignored: {ignored_locked}")


# Adds a new task from a Canvas assignment object to Todoist under the
# project corresponding to project_id
def add_new_task(assignment, project_id):
    todoist_api.add_task(
        content="[" + assignment["name"] + "](" + assignment["html_url"] + ")" + " Due",
        project_id=project_id,
        due_datetime=assignment["due_at"],
        labels=config["todoist_task_labels"],
        priority=config["todoist_task_priority"],
    )


def update_task(assignment, task):
    try:
        todoist_api.update_task(task_id=task.id, due_datetime=assignment["due_at"])
    except Exception as error:
        print(f"Error while updating task: {error}")


if __name__ == "__main__":
    main()
