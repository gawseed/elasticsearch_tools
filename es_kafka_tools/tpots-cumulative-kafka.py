#! /bin/python3

import argparse
import sys
import math
from   time     import sleep
from   json     import dumps, loads
from   kafka    import KafkaConsumer, TopicPartition
from   kafka    import KafkaProducer

global parg
timewin = 86400   # default timewindow 24 hours

topic_dict = { "parsons_gawseed_badips_tpot1"  : [],
               "parsons_gawseed_badips_tpot2" : [],
               "parsons_gawseed_badips_tpot3" : [],
               "parsons_gawseed_badips_tpot4" : [],
           }


def load_topic(topic) :
    global parg
    if parg.verbose:
        print("\nLoading topic: %s\n" % (topic))

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=['localhost:9091'],
        enable_auto_commit=True,
        group_id=parg.groupid,
        value_deserializer=lambda x: loads(x.decode('utf-8')),
        consumer_timeout_ms=5000,
    )

    # start from beginning of topic or continue from last pull
    if parg.beginning :
        if parg.verbose:
            print("Seeking to beginning")
        # poll gets a partition assigned, so we can seek in it
        consumer.poll(timeout_ms=5000)
        consumer.seek_to_beginning()

    i = 1
    for message in consumer:
        msg = message.value
        topic_dict[topic].append(msg)

        i+=1
        # do we have a input limit, 
        if ( parg.max != 0 ) and ( parg.max < i ) :
            break

        # print ("Got:  %s:%d:%d: key=%s value=%s" % 
        #        (message.topic, message.partition,
        #         message.offset, message.key,
        #         message.value))

    consumer.close()

# end load_topic(topic) :


def to_kafka_ipdict(ipdict) :
    global parg

    if parg.debug :
        for ip in ipdict.keys() :
            print("%s" % ( dumps(ipdict[ip]).encode('utf-8') ))
    else :
        producer = KafkaProducer(bootstrap_servers=['localhost:9091'],
                                 value_serializer=lambda x: 
                                 dumps(x).encode('utf-8'))

        for ip in ipdict.keys() :
            producer.send('parsons_gawseed_tpots_cumulative', value=ipdict[ip])

        producer.close()

# def to_kafka_ipdict :


# send an ipdict to kafka

def out_ipdict(ipdict) :
    # cheesebag sort, if 'count' is over 1,000,000, the results will get
    # weird. But python no longer has a 'cmp' sort because, hmm, well
    # reasons. Sort MUST be done on a single value or by using a class,
    # which in this case would be overweight.
    # Less overweight cheesebag?
    i=1
    for ip in  sorted(ipdict.keys(), 
                      key=lambda x: ipdict[x]['other_attributes']['tpots']+(ipdict[x]['other_attributes']['count']/1000000),
                      reverse=True) :
        print("%3.3d  ip: %15.15s   count: %4.4d  tpots: %d  ws: %d  we: %d" % 
              ( i, ip,
                ipdict[ip]['other_attributes']['count'],
                ipdict[ip]['other_attributes']['tpots'], 
                ipdict[ip]['other_attributes']['winstart'],
                ipdict[ip]['other_attributes']['winend'] ) )
        i+=1
# def out_ipdict :


# print out a topic list
def out_topiclist(tlist) :
    i=1
    for tpe in  tlist :
        print("%4.4d  %s ip: %15.15s    %s" % 
              ( i, tpe['timestamp'], tpe['value'], tpe['tag'] ))
        i+=1
# def out_topicdict :


# MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN MAIN

def main(argv) :

    ipdict = {};

    p = argparse.ArgumentParser()
    p.add_argument("-b", "--beginning", help="Read topics from beginning", 
                   action="store_true")
    p.add_argument("-t", "--timewin", help="Time window (seconds) to use, default 86400 (1 day)", 
                   default=86400, type=int)
    p.add_argument("-g", "--groupid", help="Kafka Group ID to use. Used to keep track of last read values. Default: \"mytpot\"", 
                   default="mytpot")
    p.add_argument("-m", "--max", help="Maximum number of mesasges to pull from each topic, for debugging", 
                   default=0, type=int)
    p.add_argument("-d", "--debug", help="Debug, send output to STDOUT, not to kafka", 
                   action="store_true")
    p.add_argument("-v", "--verbose", help="Verbose output", 
                   action="store_true")

    global parg
    parg = p.parse_args(argv)

    for topic in topic_dict.keys():
        load_topic(topic)

    mark_time=sys.maxsize
    last_time=0

    # sort topics and find oldest and newest event
    for topic in topic_dict.keys():
        # if there are any values loaded for this topic
        if len(topic_dict[topic]) > 0 :
            if parg.verbose:
                print("Sorting %s" % (topic))

            topic_dict[topic] = sorted(topic_dict[topic],
                                       key=lambda x: x['timestamp'],)
            # if parg.verbose :
            #       out_topiclist(topic_dict[topic])

            # find earliest time from all topics
            if mark_time > int(topic_dict[topic][0]['timestamp']) : 
                mark_time = int(topic_dict[topic][0]['timestamp'])
            # find most recent timestamp from all topics
            if last_time < int(topic_dict[topic][(len(topic_dict[topic])-1)]['timestamp']) : 
                last_time = int(topic_dict[topic][(len(topic_dict[topic])-1)]['timestamp'])
    #   for topic in topic_dict.keys():

    # Check if the start time is sensible
    if mark_time == sys.maxsize or mark_time <= 0 :
        print("Error: no starting timestamps found")
        sys.exit(1)

    print("\nProcessing from %s to %s" % (mark_time, last_time))
    print("   windows %d" % ( int(math.ceil((last_time - mark_time)/parg.timewin)) ))

    # prcoess topics per time window and create outgoing ipdict
    while ( mark_time < last_time ) :
        mark_end = mark_time + parg.timewin
        ipdict = {}
        print("")
        for topic in topic_dict.keys():
            tpd = {}
            print("%s list length: %d" % (topic, len(topic_dict[topic])) )

            while ( 0 < len(topic_dict[topic]) and
                    int(topic_dict[topic][0]['timestamp']) < mark_end 
            ) :
                entry = topic_dict[topic].pop(0)
                ip = entry['value']

                if ( ip in tpd ) :
                    tpd[ip]['count'] = tpd[ip]['count'] + 1
                    # find max commands_risk for this topic
                    if tpd[ip]["commands_risk"] < entry["other_attributes"]["commands_risk"] :
                        tpd[ip]["commands_risk"] = entry["other_attributes"]["commands_risk"]
                else :
                    tpd[ip] = {}
                    tpd[ip]['count'] = 1
                    tpd[ip]["commands_risk"] = entry["other_attributes"]["commands_risk"]
            #  while ( 0 < len(topic_dict[topic]) and

            for ip in tpd.keys() :
                if ip in ipdict :
                    ipdict[ip]['other_attributes']['count'] = ipdict[ip]['other_attributes']['count'] + tpd[ip]["count"]
                    ipdict[ip]['other_attributes']['tpots'] += 1
                    # find max commands_risk for all topics
                    if ipdict[ip]['other_attributes']['commands_risk'] < tpd[ip]["commands_risk"] :
                        ipdict[ip]['other_attributes']['commands_risk'] = tpd[ip]["commands_risk"]

                else :
                    ipdict[ip] = {}
                    ipdict[ip]['value']     = ip
                    ipdict[ip]['datatype']  = "ip_address"
                    ipdict[ip]['tag']       = "parsons:gawseed:cumulative:badips:tpots"
                    ipdict[ip]['other_attributes'] = {}
                    ipdict[ip]['other_attributes']['count']         = tpd[ip]["count"]
                    ipdict[ip]['other_attributes']['tpots']         = 1
                    ipdict[ip]['other_attributes']['winstart']      = mark_time
                    ipdict[ip]['other_attributes']['winend']        = mark_end
                    ipdict[ip]['other_attributes']['commands_risk'] = tpd[ip]["commands_risk"]
            # for ip in tpd.keys() :

        print("ipdict values time range: %s to %s, length: %d" %
              ( mark_time, mark_end, len(ipdict) ))
        if parg.verbose :
            out_ipdict(ipdict)

        to_kafka_ipdict(ipdict)

        mark_time += parg.timewin


if __name__ == "__main__":
    main(sys.argv[1:])
