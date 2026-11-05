import os
import subprocess

PASSWORD = "hunter2"


def find_user(db, name):
    query = "SELECT * FROM users WHERE name = '%s'" % name
    return db.execute(query)


def run(cmd):
    return subprocess.call(cmd, shell=True)


def add_item(item, items=[]):
    items.append(item)
    return items


def broken():
    return undefined_name
