#! /bin/python3

import datetime as DT
import dateutil.parser as DP
import re
import argparse
from subprocess import run, check_call, CalledProcessError, PIPE
import random
from math import floor
import json
import sys

from time import sleep

# for curl connection errors
class BadConnection(Exception):
    pass


line_re = re.compile(
    r'(?P<label>\S+) +(?P<date>\S+) +(?P<val>\d+).*'
)

#        ndate =  DP.parse( kw['date'] )


def open_ssh_tunnel(args, control_path, tp):
    cmd_list = ("ssh", "-4", "-f", "-N", "-M", "-S", control_path,
               "-L", "%d:localhost:%d" % (args.lport, args.rport), tp)
    if args.verbose :
        print("open_ssh_tunnel cmd:\n", cmd_list)

    result = run(cmd_list)

    if ( result.returncode != 0 ) :
        print( "Error: open_ssh_tunnel: ssh returned:\n  %d" %
               (result.returncode) )
        return False

    return True
# end open_ssh_tunnel

        
def close_ssh_tunnel(args, control_path, tp):
    cmd_list = ("ssh", "-S", control_path, "-O", "exit", tp)
    if args.verbose :
        print("close_ssh_tunnel cmd:\n", cmd_list)

    result = run(cmd_list)

    if ( result.returncode != 0 ) :
        print("Error: close_ssh_tunnel: ssh returned: %d" %
              (result.returncode) )

# end close_ssh_tunnel


def curl_run(args, cmd_str):
    if args.verbose :
        print("curl_run: ", cmd_str)

    try:
        run_ret = run(args=cmd_str, check=True, stdout=PIPE, stderr=PIPE)
    except CalledProcessError as cpe:
        print("Error: curl_run: unable to connect with curl!")
        print("   command: ", cmd_str)
        print("  response: %d\n  %s\n  %s" %
              (cpe.returncode, cpe.stdout, cpe.stderr))
        raise BadConnection()

    if args.verbose :
        print("  response: %s : %s" %
              (run_ret.stdout, run_ret.stderr))

    return run_ret

# end curl_run


def curl_delete_to(args, to_index):
    cmd_del_to  = ("curl", "-X", "DELETE", "http://localhost:9200/%s/" %
                   ( to_index ))
    
    curl_delete_to = curl_run(args, cmd_del_to)

# end curl_delete_to


def curl_copy(args, from_index, to_index):
    # prepare the TO index
    # create index
    cmd_create =  ("curl", "-X", "PUT",
                   "http://localhost:9200/%s" % ( to_index ))
    
    # Not checking resposne, Errors should be caught during copy
    curl_run(args, cmd_create)
    
    # change total_fields limit from ES default 1000 to TPOT s/w's 2000
    cmd_add = ("curl", "-X", "PUT", 
               "http://localhost:9200/%s/_settings" % ( to_index ),
               "-H", "Content-Type: application/json", "-d",
               "{ \"index.mapping.total_fields.limit\": 2000 }")

    # Not checking response, Errors should be caught during copy
    curl_run(args, cmd_add)
    
    cmd = ("curl", "-X", "POST", "http://localhost:9200/_reindex?pretty", "-H", "Content-Type: application/json", "-d", "{ \"source\": { \"remote\": { \"host\": \"http://localhost:%d\" }, \"index\": \"%s\", \"query\": { \"match_all\": {} } }, \"dest\": { \"index\": \"%s\" } }" % ( args.lport, from_index, to_index ) )
    
    curl_copy_run = curl_run(args, cmd)

    curl_copy_d = json.loads(curl_copy_run.stdout)

    if ( not "created" in curl_copy_d) :
        print("Error: curl_copy: copy failed:\n  %s" % (curl_copy_run.stdout))
    else :
        print("    Documents Created: %d" % (curl_copy_d["created"]))

    if ( ( "failures" in curl_copy_d ) and 
         ( len(curl_copy_d["failures"]) > 0 ) )  :
        print("    Failures found: %d" % ( len(curl_copy_d["failures"]) ))
        for fail in curl_copy_d["failures"] :
            print(fail)
    
# end curl_copy



def curl_check_copy(args, from_index, to_index):
    cmd_to   = ("curl", "-X", "GET", "http://localhost:9200/%s/_count" %
                ( to_index ) )
    
    cmd_from = ("curl", "-X", "GET", "http://localhost:%d/%s/_count" %
                ( args.lport, from_index ) )
    
    run_to   = curl_run(args, cmd_to)
    run_from = curl_run(args, cmd_from)

    run_to_d   = json.loads(run_to.stdout)
    run_from_d = json.loads(run_from.stdout)
        
    if ( not "count" in run_from_d ) :
        print("  Index Not Found: Skipping: \'%s\'\n" %
              (from_index))
    elif ( not "count" in run_to_d ) :
        print("  Copying:  %s:%d" %  (from_index, run_from_d["count"]))
        curl_copy(args, from_index, to_index)
    elif ( run_from_d["count"] == run_to_d["count"] ) :
        print("  Exists already: Skipping: %d == %s:%d" %
              (run_from_d["count"], to_index, run_to_d["count"]))
    elif ( run_from_d["count"] > run_to_d["count"] ) :
        print("  Deleting and Copying: document sizes do not match:")
        print("    %s:%d > %s:%d" %
              (from_index, run_from_d["count"],
               to_index, run_to_d["count"]))
        curl_delete_to(args, to_index)
        curl_copy(args, from_index, to_index)
    else :
        print("ERROR: nuts!, should not happen: %s:%d < %s:%d" %
              (from_index, run_from_d["count"],
               to_index,   run_to_d["count"]))

# end curl_check_copy


    
# MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN


# setup variables

clparse = argparse.ArgumentParser(description="Using curl commands to copy a ES index(es) to a local ES");

clparse.add_argument('--start_date', '-s',
                     help='The date to start copying indexes from, used for index name. Can not be newer than 2 days ago (default).')
clparse.add_argument('--end_date', '-e',
                     help='Date string to end copying indexes from. Can not be newer than 2 days ago (default). If no --start_date is given, this will be the only day tried.')
clparse.add_argument('--tpots', '-t', default="tpot,tpot2,tpot3,tpot4",
                     help='comma delimited list of tpots to copy from')
clparse.add_argument('--verbose', '-v', action='store_true', default=False,
                     help='verbose output')
clparse.add_argument('--lport',
                     default=( floor(64000*random.random()) + 1024 ),
                     help='local port to use for ssh tunnel (random)')
clparse.add_argument('--rport', default=64298,
                     help='remote port to use for ssh tunnel (64298)')
clparse.add_argument('--defaults', '-D', action='store_true', default=False,
                     help='show default command line values')

args=clparse.parse_args()

if args.defaults :
    print("\nCommand Line Defaults: ")
    print( {key: clparse.get_default(key) for key in vars(args)} )
    print("Current: ", vars(args), "\n")

if args.tpots :
    tpots_list = args.tpots.split(',')

    
days2_dlt = DT.timedelta(days = 2)
day_dlt   = DT.timedelta(days = 1)
end_dt    = DT.datetime.now() - days2_dlt


if args.end_date :
    user_end_dt = DP.parse( args.end_date )
    if ( end_dt < user_end_dt ) :
        print("Error: --end_date cannot be newer than 2 days ago:\'")
        print("       Entered end date: ", user_end_dt)
        print("           Two days ago: ", end_dt)
        exit(1)
    else :
        end_dt = user_end_dt

if args.start_date :
    start_dt = DP.parse( args.start_date )
else :
    start_dt = end_dt

if args.verbose :
    print("start date: ", start_dt)
    print("  end date: ", end_dt)


# start work

for tp in tpots_list :
    print("\nConnecting to: %s" % str(tp))  # separate tpot output
    
    ssh_ctrl_path = "/tmp/%s:%d:%%p" % (tp, floor(random.random()*999999))

    try:
        if not open_ssh_tunnel(args, ssh_ctrl_path, tp) :
            continue

        wh_dt = start_dt
        while wh_dt <= end_dt :
            from_index = ("logstash-%4.4d.%2.2d.%2.2d" %
                          (wh_dt.year, wh_dt.month, wh_dt.day) )
            to_index   = "%s-%s" % (tp, from_index)

            print("%s: %s  to localhost: %s" % ( tp, from_index, to_index ) )
            sys.stdout.flush()

            try:
                curl_check_copy(args, from_index, to_index)
            except BadConnection:
                print("\nError: failed to connect to %s" % (tp))
                print("         skipping the rest of coyping for %s\n" % (tp))
                break
            
            wh_dt += day_dlt

        close_ssh_tunnel(args, ssh_ctrl_path, tp)

    except Exception as e:
        close_ssh_tunnel(args, ssh_ctrl_path, tp)
        raise e

