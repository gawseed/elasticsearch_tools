#!/usr/bin/env python

#
# Used to convert elasticsearch queries to fsdb format
#
# python requirements:
# up to date (i.e. pip3 install) elasticsearch
# up to date                     pyOpenSSL
#

import argparse
import sys
from elasticsearch import Elasticsearch
import json
from collections import defaultdict, MutableMapping
import pandas as pd
import json
import ast
import dateutil.parser
import datetime

SCROLL_WAIT = '30s'
SCROLL_SIZE = 10000

def name_value(s):
    usagestr = "name:value"
    try:
        x, y = map(str, s.split(':'))
        if (not x) or (not y):
            raise Exception('Option error')
        x_safe = bytes(x, "utf-8").decode("unicode_escape")
        y_safe = bytes(y, "utf-8").decode("unicode_escape")
        return { "name":x_safe, "value":y_safe }
    except:
        raise argparse.ArgumentTypeError(usagestr)

def construct_condition_str(paramlist):
    outstr = ""
    sep =""
    if paramlist:
        for m in paramlist:
            if outstr != "":
                sep = ","
            outstr += '%s{"match":{"%s" : "%s"}}' % (sep, m["name"], m["value"])
    return outstr

def construct_date_str(paramlist):
    outstr = ""
    sep =""
    if paramlist:
        for m in paramlist:
            if outstr != "":
                sep = ","
            outstr += '%s "%s":"%s"' % (sep, m["name"], m["value"])
    return outstr

# https://www.geeksforgeeks.org/python-convert-nested-dictionary-into-flattened-dictionary/
def convert_flatten(d, parent_key ='', sep ='_'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            items.extend(convert_flatten(v, new_key, sep = sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def parse_date_if_possible(x):
    dt = x
    if dt.isnumeric():
        # https://stackoverflow.com/questions/23929145/how-to-test-if-a-given-time-stamp-is-in-seconds-or-milliseconds
        if len(dt) > 12:
            dt = datetime.datetime.fromtimestamp(int(dt) / 1000)
        else:
            dt = datetime.datetime.fromtimestamp(int(dt))
    try:
        return dateutil.parser.parse(str(dt)).strftime('%s')
    except:
        return dt

def do_extract(parg):

    # Construct various conditional prases
    muststr = construct_condition_str(parg.must)
    mustnotstr = construct_condition_str(parg.mustnot)
    shouldstr = construct_condition_str(parg.should)
    daterangestr = construct_date_str(parg.daterange)

    datestr_template = '{"range" : { "%s" : { %s } }}'
    if daterangestr:
        # Prefix date range phrase to muststr
        date_phrase =  datestr_template % (parg.timecol, daterangestr)
        if muststr != "":
            muststr = date_phrase + "," + muststr
        else:
            muststr = date_phrase

    # Construct the query string
    #querystr_template = '{"query":{"bool":{"must":[%s, %s],"must_not":[%s],"should":[%s]}}}'
    querystr_template = '{"query":{"bool":{"must":[%s],"must_not":[%s],"should":[%s]}}}'
    querystr = querystr_template % (muststr, mustnotstr, shouldstr)
    #print(querystr, parg.index)

    urlpfxstr = ""
    if parg.urlpfx:
        urlpfxstr = "es"

    if parg.insecure:
        es = Elasticsearch([{'host': parg.eshost, 'port': parg.esport,
                            'url_prefix': urlpfxstr, 'use_ssl': True}],
                            use_ssl=True, verify_certs=False,
                            timeout=30, max_retries=10, retry_on_timeout=True)
    else:
        es = Elasticsearch([{'host': parg.eshost, 'port': parg.esport,
                            'url_prefix': urlpfxstr}], timeout=30,
                            max_retries=10, retry_on_timeout=True)

    # Do the actual query
    results = None
    res = es.search(index=parg.index, size=SCROLL_SIZE, body=querystr, request_timeout=30, scroll = SCROLL_WAIT)
    if res:
        results = []
        old_scroll_id = res['_scroll_id']
        while len(res['hits']['hits']):
            new_res = [d for d in res['hits']['hits']]
            results.extend(new_res)
            if(parg.size > 0 and len(results) >= parg.size):
                results = results[:parg.size]
                break
            res = es.scroll(
                scroll_id = old_scroll_id,
                scroll = SCROLL_WAIT
            )
            old_scroll_id = res['_scroll_id']

    return results
    
def write_to_fsdb(outfile, data, fields, addheader, flatten, timecol):

    vals = defaultdict(list)

    #df = pd.DataFrame()

    print("Flattening Results")
    cols = []
    rowdicts = []
    for d in data:
        rec = {}
        if "_source" in d.keys():
            dstruct = d["_source"]
            for k in dstruct.keys():
                fval = str(dstruct[k]).strip().replace('\n', ' ').replace('\r', '').replace('\\n', ' ')
                if flatten:
                    try:
                        dval = ast.literal_eval(fval)
                        dval = convert_flatten(dval)
                        for fk in dval.keys():
                            rec[k+"_"+fk] = str(dval[fk])
                    except:
                        rec[k] = fval
                else:
                    rec[k] = fval
            # Delete keys that don't exist in selection list
            if fields:
                for k in list(rec.keys()):
                    if k not in fields:
                        del rec[k]
            rowdicts.append(rec)
            cols.extend(list(rec.keys()))
            cols = list(set(cols))
    # Move timestamp to the first column
    if timecol in cols:
        cols.remove(timecol)
        cols.insert(0, timecol)
    rows = []
    for r in rowdicts:
        val = []
        for c in cols:
            if c in r.keys():
                val.append(r[c])
            else:
                val.append("")
        rows.append(val)

    df = pd.DataFrame(rows, columns=cols)
    headers = list(df.columns)

    # Transform time field
    if timecol in headers:
        print("Sorting Results.")
        df = df.loc[df[timecol] != "0"]
        # ISO 8601 format date
        df[timecol] = df[timecol].apply(lambda x: parse_date_if_possible(x))
        df = df.astype({timecol: 'int64'})
        # Sort values
        df.sort_values(by=[timecol], inplace=True)
    else:
        print("WARNING: Did not find %s in header. Not transforming" % (timecol))


    print("Writing results to file.")
    with outfile as fp:
        if addheader:
            #hdrstr = "#fsdb -F C|"
            hdrstr = "#fsdb -F t"
            for h in headers:
                hdrstr += " %s" % (h)
            fp.write(hdrstr + '\n')
        #df = df.replace(r'\\r', '', regex=True)
        #df.to_csv(path_or_buf=fp, sep='|', header=False, index=False)
        df.to_csv(path_or_buf=fp, sep='\t', header=False, index=False)


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("-e", "--eshost", help="Elasticsearch host (default=localhost)", default='localhost')
    p.add_argument("-p", "--esport", help="Elasticsearch port (default=9200)", default=9200)
    p.add_argument("-i", "--index", help="Elasticsearch index (default=_all)", default="_all")
    p.add_argument("-s", "--size", help="Return size", default=0, type=int)
    p.add_argument("-t", "--timecol", help="Time Field", type=str, default="@timestamp")
    p.add_argument("-M", "--must", help="Field that must match (logical AND)", action='append', type=name_value)
    p.add_argument("-X", "--mustnot", help="Field that must not match (logical NOT)", action='append', type=name_value)
    p.add_argument("-S", "--should", help="Field that should match (logical OR)", action='append', type=name_value)
    p.add_argument("-D", "--daterange", help="Specifiy date range", action='append', type=name_value)
    p.add_argument("-F", "--fields", help="Returned fields", action="append", type=str)
    p.add_argument("-B", "--flatten", help="Flatten indexes", action="store_true")
    p.add_argument("-H", "--addheader", help="Add FSDB header", action="store_true")
    p.add_argument("-I", "--insecure", help="Don't verify certs", action="store_true")
    p.add_argument("-U", "--urlpfx", help="Use the 'es' prefix in the URL", action="store_true")
    p.add_argument("-o", "--outfile", help="Output file", type=argparse.FileType('w'), default="-")

    parg = p.parse_args(argv)
    data = do_extract(parg)
    if not data:
        print("Query to elasticsearch failed")
        exit(1)

    #datastr = json.dumps(data)
    #print(datastr)
    write_to_fsdb(parg.outfile, data, parg.fields, parg.addheader, parg.flatten, parg.timecol)

    exit(0)
    

if __name__ == "__main__":
    main(sys.argv[1:])
