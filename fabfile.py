import os
import sys
import glob
import datetime
import erppeek
import xmlrpclib

from fabric.api import task, hosts
from fabric.api import local, env, prompt, execute, lcd, run, put
from fabric.context_managers import quiet
from fabric import colors

# see: http://fabric.readthedocs.org/en/1.8/usage/execution.html#leveraging-native-ssh-config-files
env.use_ssh_config = True

env.TS              = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
env.odoo_database   = os.environ.get("ODOO_DATABASE", "wochenbericht")
env.odoo_admin_user = os.environ.get("ODOO_ADMIN_USER", "admin")
env.odoo_admin_pw   = os.environ.get("ODOO_ADMIN_PASS", "12345")
env.odoo_modules    = ["wochenbericht"]
env.odoo_location   = os.path.expanduser("~/develop/nexiles/odoo")
env.odoo_snapshot   = "sql/{odoo_database}-snapshot-{TS}.dump".format(**env)

def get_last_snapshot():
    # Try to get latest snapshot
    snapshots = glob.glob("sql/{odoo_database}-snapshot*.dump".format(**env))
    if snapshots:
        env.latest_snapshot = snapshots[-1]

def set_database_name(database):
    if hasattr(set_database_name, "firstrun"):
        print colors.yellow("Setting database: {}".format(database))
    set_database_name.firstrun = True
    env.odoo_database   = database
    env.odoo_snapshot   = "sql/{odoo_database}-snapshot-{TS}.dump".format(**env)
    get_last_snapshot()

def get_odoo_client():
    return erppeek.Client("http://localhost:8069", db=env.odoo_database, user=env.odoo_admin_user, password=env.odoo_admin_pw)

set_database_name(env.odoo_database)

if not os.path.exists(os.path.join(env.odoo_location, "odoo.py")):
    print colors.red("No odoo checkout found in {odoo_location} -- abort".format(**env))
    sys.exit(10)

######################################################################
# Building
@task
def build():
    """Build module"""
    # nothing fancy for now
    with lcd("docs"):
        local("make html")
    local("rst2html.py docs/changelog.rst > src/nexiles_odoo/static/description/index.html")

######################################################################
# Development tasks
@task(alias="start")
def start_odoo(database=None, update=None):
    """Fire up odoo"""
    if database:
        set_database_name(database)
    if not update:
        local("{odoo_location}/odoo.py --addons-path ./addons,{odoo_location}/addons --database {odoo_database}  --logfile=odoo.log".format(**env))
    else:
        print colors.red("Updating modules: {}".format(update))
        local("{odoo_location}/odoo.py --addons-path ./addons,{odoo_location}/addons --database {odoo_database} --update {update} --logfile=odoo.log".format(update=update, **env))

@task
def replay(database=None, update=None):
    """Instant Replay -- restore to last snapshot and startup odoo."""
    if database:
        env.odoo_database = database
        get_last_snapshot()
    execute(restore)
    execute(start_odoo, database, update)

@task
def snapshot(database=None):
    """Snapshot database"""
    if database:
        set_database_name(database)
    # NOTE:
    # the x and O options basically ignore users and permissions.
    # This is probably a bad idea in production ....
    local("pg_dump -x -O -Fc -f {odoo_snapshot} {odoo_database}".format(**env))

@task
def restore(database=None):
    """Restore to newest snapshot"""
    if database:
        set_database_name(database)

    if "latest_snapshot" not in env:
        print colors.red("No snapshot found -- abort.")
        return

    print colors.yellow("I'm going to drop the database {odoo_database} and restore from {latest_snapshot}.".format(**env))
    prompt(colors.red("press enter to continue"))

    local("dropdb {odoo_database}".format(**env))
    local("createdb -T template0 {odoo_database}".format(**env))
    local("pg_restore -O -d {odoo_database} {latest_snapshot}".format(**env))

@task(alias="update")
def update_modules(database=None, modules=None):
    """Update modules.  Requires running odoo."""
    if database is not None:
        set_database_name(database)

    if modules is not None:
        env.odoo_modules = modules.split(":")

    client = get_odoo_client()
    try:
        client.upgrade(*env.odoo_modules)
    except xmlrpclib.Fault, e:
        print colors.red("XMLRPC ERROR")
        print colors.yellow(e.faultCode)
        print colors.yellow(e.faultString)

# EOF