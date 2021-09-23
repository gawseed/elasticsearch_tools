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
import os

from time import sleep

# for curl connection errors
class BadConnection(Exception):
    pass


line_re = re.compile(
    r'(?P<label>\S+) +(?P<date>\S+) +(?P<val>\d+).*'
)

#        ndate =  DP.parse( kw['date'] )


def open_ssh_tunnel(args, control_path, host):
    cmd_list = ("ssh", "-4", "-f", "-N", "-M", "-S", control_path,
                "-L", "%d:localhost:%d" % (args.lport, args.rport), host)
    if args.verbose :
        print("open_ssh_tunnel cmd:\n", cmd_list)

    result = run(cmd_list)

    if ( result.returncode != 0 ) :
        print( "Error: open_ssh_tunnel: ssh returned:\n  %d" %
               (result.returncode) )
        return False

    return True
# end open_ssh_tunnel

        
def close_ssh_tunnel(args, control_path, host):
    cmd_list = ("ssh", "-S", control_path, "-O", "exit", host)
    if args.verbose :
        print("close_ssh_tunnel cmd:\n", cmd_list)

    result = run(cmd_list)

    if ( result.returncode != 0 ) :
        print("Error: close_ssh_tunnel: ssh returned: %d" %
              (result.returncode) )

# end close_ssh_tunnel


def curl_run(args, cmd_str, ctext=False):
    if args.verbose :
        print("curl_run: ", cmd_str)

    try:
        run_ret = run(args=cmd_str, check=True, stdout=PIPE, stderr=PIPE, 
                      universal_newlines=True)
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
    if args.num : args.num = args.num - 1 
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


def curl_get_indices(args):
    cmd_ind_ls   = ("curl", "-X", "GET",
                    "http://localhost:%d/_cat/indices/" % ( args.lport) )
#                    "http://localhost:%d/_cat/indices/" % ( 9200 ) )
    
    run_ind_ls  = curl_run(args, cmd_ind_ls, ctext=True)

    index_list = [ re.sub(r'^\s*\w+\s+\w+\s+(\S+)\s.*$', r'\g<1>' , li) 
                   for li in run_ind_ls.stdout.splitlines() ]

    if args.exclude_override :
        ex_str = "^(users|\.)"
    else :
        ex_str = "^(users|\.|filebeat|metricbeat)"

    if args.exclude :
        ex_str = "%s|%s" % (ex_str, args.exclude)

    re_filter = re.compile(ex_str)

    index_filt_list = [i for i in index_list if not re_filter.search(i)]

    if args.include :
        ri_filter = re.compile(args.include)
        index_filt_list = [i for i in index_filt_list if ri_filter.search(i)]

    if args.sort :
        index_filt_list.sort(reverse=args.reverse,key=ugo_sort)

    return(index_filt_list)

# end curl_get_indices


def ugo_sort(kv):
    ugo_re = re.compile(
        r'(?P<name>.+-)\d\d(?P<year>\d\d)\.(?P<month>\d+)\.(?P<day>\d+)')
    m = ugo_re.match(kv)
    if m :
        n = re.match(r'.*(?P<num>\d*).*', m.group("name"))
        if n :
            if n.group("num") == "" :
                num = 0
            else :
                num = int(n.group("num"))*1000000

            val = num + (int(m.group("year"))*10000) + (int(m.group("month"))*100) + int(m.group("day"))
        else :
            val = 0
    else :
        val = 0
    
    return(val)


def elasticdump(args, index_list, ctext=False):
    if args.verbose : print("elasticdump")
    
    for index in index_list :
        
        path_file_name = args.dump_dir + "/" + args.prefix + index + ".json"

        cmd_str = ( "elasticdump", "--input=http://localhost:9200/%s" % (index),
                    "--output=%s" % (path_file_name) )

        print("elasticdump: dumping: \'%s\'" % (index))

        if ( os.path.exists(path_file_name) ) :
            print("    WARNING: File Exists, Skipping: %s\n" % (path_file_name))
            continue

        print("                  to: \'%s\'" % (path_file_name) )

        try:
            run_ret = run(args=cmd_str, check=True, stdout=PIPE, stderr=PIPE, 
                          universal_newlines=True)
            
        except CalledProcessError as cpe:
            print("Error: elasticdump: dump failed!")
            print("   command: ", cmd_str)
            print("  response: %d\n  %s\n  %s" %
                  (cpe.returncode, cpe.stdout, cpe.stderr))
            raise Exception("elasticdump fail")

        if args.verbose :
            print("  response: %s : %s" %
                  (run_ret.stdout, run_ret.stderr))

    # end for

# elasticdump

    
# MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN


# setup variables

clparse = argparse.ArgumentParser(description="Using curl commands to copy a ES index(es) to a local ES");

clparse.add_argument('--hosts', '-s', default="pumpkin",
                     help='comma delimited list of ssh (host) names to copy indexes from')
clparse.add_argument('--verbose', '-v', action='store_true', default=False,
                     help='verbose output')
clparse.add_argument('--lport', type=int,
                     default=( floor(64000*random.random()) + 1024 ),
                     help='local port to use for ssh tunnel (random)')
clparse.add_argument('--rport', type=int, default=9200,
                     help='remote port to use for ssh tunnel (9200)')
clparse.add_argument('--num', '-n', type=int, default=0,
                     help='Maximum number of indexes to attempt to copy')
clparse.add_argument('--list', '-l', action='store_true', default=False,
                     help='list indices')
clparse.add_argument('--sort', '-S', action='store_true', default=False,
                     help='Sort the list of indices, ascending')
clparse.add_argument('--reverse', '-r', action='store_true', default=False,
                     help='Reverse the sort')
clparse.add_argument('--prefix', '-p', default="",
                     help='Prefix to add to index name, default is host name')
clparse.add_argument('--include', '-i', 
                     help='Regex of indices to copy, default is all')
clparse.add_argument('--exclude', '-e', 
                     help='Regex of indices to exclude. (users|\.|filebeat|metricbeat) always excluded.')
                    # override includes filebeat and metricbeat 
clparse.add_argument('--exclude_override', '-E', action='store_true', 
                     default=False, help=argparse.SUPPRESS)
clparse.add_argument('--defaults', '-D', action='store_true', default=False,
                     help='show default command line values')
clparse.add_argument('--dump', '-d', action='store_true', default=False,
                     help='Dump indexes to file using elasticdump. Pulls from localhost!')
clparse.add_argument('--dump_dir', default="./",
                     help='Dump indexes to this directory (./)')

args=clparse.parse_args()

if args.defaults :
    print("\nCommand Line Defaults: ")
    print( {key: clparse.get_default(key) for key in vars(args)} )
    print("Current: ", vars(args), "\n")

counting = False    
if args.num > 0 : counting = True


if args.dump :
    args.lport = 9200
    index_list = curl_get_indices(args)

    if args.list :
        print("\nList of file that WOULD dump to '%s':\n" % (args.dump_dir) )
        print(index_list)
        sys.exit(1);

    print("\nDumping to '%s':\n" % (args.dump_dir) )
    elasticdump(args, index_list)
    
    sys.exit(1);



if args.hosts :
    hosts_list = args.hosts.split(',')

    
# start work

for host in hosts_list :
    print("\nConnecting to: %s" % str(host))  # separate tpot output
    
    ssh_ctrl_path = "/tmp/%s:%d:%%p" % (host, floor(random.random()*999999))

    try:
        if not open_ssh_tunnel(args, ssh_ctrl_path, host) :
            continue

        index_list = curl_get_indices(args)

        if args.list :
            print("\nIndexes:\n")
            print(index_list)
            continue

        for index in index_list :
            from_index = index
            if args.prefix :
                to_index =  "%s-%s" % (args.prefix, index)
            else :
                to_index = "%s-%s" % (host, index)

            print("%s: %s  to localhost: %s" % ( host, from_index, to_index ) )
            sys.stdout.flush()

            try:
                curl_check_copy(args, from_index, to_index)
                if counting :
                    if args.num <= 0 :
                        print("\nReached maximum attempts set\n")
                        break
                    else :
                        print("%d attempts left" % (args.num))
                        
            except BadConnection:
                print("\nError: failed to connect to %s" % (host))
                print("         skipping the rest of coyping for %s\n" % (host))
                break
            
        close_ssh_tunnel(args, ssh_ctrl_path, host)

    except Exception as e:
        close_ssh_tunnel(args, ssh_ctrl_path, host)
        raise e

