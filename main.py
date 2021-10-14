from datetime import datetime
import re
import csv
import os
import time

import requests
from bs4 import BeautifulSoup
import bs4.element

import secret

base_url = "https://sweb.student.iaik.tugraz.at"
home_url = base_url + "/snp/index.php"

username = secret.user
password = secret.pw

s = requests.session()


def getWebpage(url):
    global s
    resp = s.get(url)

    if resp.status_code != 200:
        return False

    return resp.content


def login():
    global s
    url = home_url + "?page=login"
    s.post(url, {"username": username, "password": password, "button": "Login"})


def getAssignmentInfo(requested_assignment):
    url = home_url + "?page=details"

    data = {}

    content = getWebpage(url)
    soup = BeautifulSoup(content, features="html.parser")

    data = getAssignmentDataFromTable(soup, requested_assignment)
    assert data != None, "can't get assignment data"

    data |= getAssignmentDataFromLogfile(data["logFileUrl"])
    del data["logFileUrl"]

    data["timeToDeadline"] = getTimeUntilDeadline(soup)

    return data


def getAssignmentDataFromLogfile(log_file_url):
    content = getWebpage(log_file_url).decode()

    if content == '=== WARNING! This is only the test log for the sanity checks! ===\n===  Any statement about points in this log file is only an   ===\n===  artifact and not related to the actual points you get.   ===\n===  This file is only intended to help you through basic     ===\n===  problems during your implementation.                     ===\n===  Your actual points score is shown in your details page.  ===\n\n':
        return {"logFileStatus": "failed"}

    # find date and commit hash
    date_regex = r"\w{3} \d\d \d\d:\d\d:\d\d"
    test_date, commit_hash = re.findall(r"^(%s) commit ([\w]*)$" % (date_regex,), content, re.MULTILINE)[0]

    # add year
    test_date = str(datetime.today().year) + " " + test_date
    # make date to datetime
    test_date = datetime.strptime(test_date, "%Y %b %d %X")

    commit_name = re.findall(r"^%s {5}(.*)$" % (date_regex,), content, re.MULTILINE)[0]

    summary_data = re.findall(r"^Summary: (\d+) OK; (\d+) FAIL$", content, re.MULTILINE)[0]
    summary = {
        "OK": summary_data[0],
        "FAIL": summary_data[1]
    }

    # find lines of log
    lol = re.findall(r"^You generated '(\d+)' lines of log.*?$", content, re.MULTILINE)[0]

    return {
        "commitHash": commit_hash,
        "commitName": commit_name,
        "testDate": test_date,
        "summary": summary,
        "lol": lol,
        "logFileStatus": "success"
    }


def getTimeUntilDeadline(soup):
    return float(soup.find("p").contents[-1][2:][:4])


def getAssignmentDataFromTable(soup, requested_assignment):
    points_table = soup.find("table")
    points_table_tmp = [row.find_all(["th", "td"""]) for row in
                        points_table.find_all("tr")]  # split the rows into cells

    points_table = {
        "header": points_table_tmp[0],
        "sanity_checks": points_table_tmp[1],
        "last_submission": points_table_tmp[2],
        "current_points": points_table_tmp[3],
        "points_total": points_table_tmp[4],
    }

    for column_index, header_cell in enumerate(points_table["header"]):
        if len(header_cell.contents) == 0:  # skip first column
            continue

        header_cell_content = header_cell.contents[0]

        if type(header_cell_content) == bs4.element.Tag:  # header cell is a assignment
            assignment_number = header_cell_content.contents[0]
            if requested_assignment == assignment_number:

                if len(points_table["current_points"][column_index].contents[0].contents) == 0:
                    isTagged = False
                    current_points = 0
                else:
                    current_points_str = points_table["current_points"][column_index].contents[0].contents[0]
                    isTagged, current_points = _checkIfAssignmentIsTaged(current_points_str)

                return {
                    "sanityPoints": float(points_table["sanity_checks"][column_index].contents[0].contents[0]),
                    "itTagged": isTagged,
                    "currentPoints": current_points,
                    "totalPoints": int(points_table["points_total"][column_index].contents[0]),
                    "logFileUrl": base_url + points_table["sanity_checks"][column_index].contents[0].attrs["href"]
                }

    return None


def _checkIfAssignmentIsTaged(string):
    if string[-1] == "*":
        return False, float(string[:-1])
    else:
        return True, float(string)


if __name__ == "__main__":
    login()

    assignment = input("which assignment do you want to scape: ")

    data_file = f"assignment_{assignment}.csv"
    data_file_exists = os.path.exists(data_file)

    fieldnames = ("sanityPoints", "itTagged", "currentPoints", "totalPoints", "commitHash",
                  "commitName", "testDate", "summary", "lol", "logFileStatus", "timeToDeadline")

    while True:
        print("scrape data")
        data = getAssignmentInfo(assignment)

        print("write data into ", end="")
        if not data_file_exists:
            print("new file")
            data_file_exists = 1
            with open(data_file, "w") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(data)
        else:
            print("existing file")
            with open(data_file, "a") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow(data)

        print("go to sleep")
        time.sleep(10)
