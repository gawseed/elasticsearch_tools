#! /bin/perl

use Getopt::Std;
use strict;
# use Data::Dumper;

# kafka binaries path
my $KPATH="/home/kafka/kafka/bin";

# regex filter
my $RE_FILTER='(192\.94\.214\.|50\.211\.142\.20[1-6]|75\.101\.48\.145|8\.8\.8\.8)';

my %opts = ();

# default to the original destination
$opts{B} = "tpot";

# default to 1 day
$opts{d} = 1;
# default search size
$opts{n} = 100000;
# default ES port to use
$opts{e} = 64297;

# base kafka Topic to fill
my $base_kafka_topic = "parsons_gawseed_badips_tpot";

# local port and control path for ssh tunnel
my $loc_port = int(rand(64000) + 1025);
my $ssh_control_path = "/tmp/" . int(rand(999999)) . ":%r:%p";

# es-to-fsdb error out
my $error_log = "/tmp/tpot-to-kafka-" . int(rand(999999)) . "-error.log";


sub print_help {
        print "\n$0: [options] -t tag ssh-hostname\n";
        print "pull tpot bad ip address from <ssh-hostname> and place them into a kafka stream\n";
        print "\t<ssh-hostname>, e.g. \'Host\' in .ssh/config, REQUIRED\n";
        print "\t-t tag\tTag to add to the JSON, definition, REQUIRED\n";
        print "\t\te.g. \'parsons:gawseed:badips:tpot1\'\n";
        print "\n";
#       print "\t-l location\tThe ssh location, e.g. \'Host\' in .ssh/config, def \'$opts{l}\'\n";
        print "\t-b Do NOT write to base kafka topic \'$base_kafka_topic\'\n";
        print "\t-e ES_port\tThe default ElasticSearch port to use on the remote machine, def \'$opts{e}\'\n";
        print "\t-k kafka-topic\tWrite JSON stream to the additional kafka feed topic \'kafka-topic\'\n";
        print "\t-d days\tDays back to search on tpot\, def: \'$opts{d}\'\n";
        print "\t-n int\tmax results from ES, def: \'$opts{n}\'\n";
        print "\t-s \tprint output to STDOUT instead of kafka\n";
        print "\t-i \tDo not use ssl for es-to-fsdb elasticsearch connection\n";
        print "\t-E error_log\tsend Std Error to this file (hint: \"&1\" will go std out) \n";
        print "\t-D \tprint Debug output to STDOUT (e.g. extra verbose)\n";
        print "\t-v \tprint Verbose output to STDOUT\n";
}

sub get_args {
    if ( ! getopts("k:t:e:n:d:E:iDsvhHuU", \%opts) ||
         ! exists $opts{t } || 
         exists $opts{h} || exists $opts{H} || 
         exists $opts{u} || exists $opts{U}    ) {
        print_help();
        exit 1;
    }
    # ssh-hostname required
    if ( 0 > $#ARGV ) {
        printf STDERR "Error: ssh-hostname required!\n";
        print_help();
        exit 1;
    }
    # old option, keep using
    $opts{l} = "$ARGV[0]";

    # don't send duplicate data to same stream
    if ( exists $opts{k} && ! exists $opts{b} &&  "$opts{k}" eq "$base_kafka_topic" ) {
        delete($opts{k});
    }
    
    # debug includes verbose
    if ( exists $opts{D} ) { $opts{v} = 1; }

    # default to using SSL for es-to-fsdb connection
    if ( exists $opts{i} ) { $opts{i} = "";   } 
    else                   { $opts{i} = "-I"; }

    # es-to-fsdb error out
    if ( exists $opts{E} ) { $error_log = "$opts{E}"; }

} # get_args

my $countip = 0;
my $countas = 0;
my %ipToAS = ();

sub get_asn (@) {
    my $ip = $_[0];
#   my $ip = "50.133.52.223";

    printf "searching for $ip\n";
    if ( exists $ipToAS{"$ip"} ) {
        $countip++;
        printf " : \'%s\' : $countip : $countas\n", $ipToAS{"$ip"};
        return  $ipToAS{"$ip"};
    }

    open( ESAS, "whois $ip | grep origin | awk -FAS '{print $2}' |" ) ||
        die "$0: Error: unable to open elasticsearch AS search: $!\n";
    # just grab the first value
    my $line = <ESAS>;
    my $ret = int($line);
    if ( $ret <= 0 ) { $ret = ""; }
    else             { $countas++; }
    close (ESAS);

    chomp $line; $countip++;
    print "\'$line\' : \'$ret\' : $countip : $countas\n";
    $ipToAS{"$ip"} = "";
    return $ret
} # get_asn


my %ipPriorityCache = ();

sub get_priority (@) {
    my $ip = $_[0];
    my $ret = "0";  # no command seen

    if ( exists $ipPriorityCache{"$ip"} ) {
        if ( exists $opts{D} ) {
            printf " get_priority: Priority Cache Hit:  $ip : \'%s\'\n",
                $ipPriorityCache{"$ip"}
        }
        return  $ipPriorityCache{"$ip"};
    }

    open( ESP, "python3 $ENV{HOME}/bin/es-to-fsdb.py  -p $loc_port $opts{i} -U -B -H  -F \"\@timestamp\" -F \"input\" -s 100 -M \"type:Cowrie\" -M \"src_ip:$ip\" -M \"eventid:cowrie.command.input\" -o - 2>$error_log |" ) ||
        die "$0: Error: unable to open elasticsearch for commands priority search $!\n";

    my @CMD = <ESP>;
    close (ESP);

    @CMD = grep s/^\d+\s+(.*)/$1/, @CMD;
    if ( 0 <= $#CMD ) {
        $ret = "3"; # commands seen


        my @BADC = grep /rm|passwd/, @CMD;

        if ( exists $opts{v} ) {
            printf "get_priority: $ip : cmds bad/good: %d/%d\n",
                (1+$#BADC), (1+$#CMD);
        }
        if ( 0 <= $#BADC ) {
            $ret = "6"; # bad commands seen
            # note: if Debug is on, Verbose should automatically be on
            if ( exists $opts{D} ) {
                chomp @BADC;
                while ( <@BADC> )  { printf "\t$_\n"; }
            }
        }
    }

    $ipPriorityCache{"$ip"} = $ret;
    return $ret;
} # get_asn


# Open an ssh tunnel from a local $loc_port (randomly created eariler)
# to $opts{l}:$opts{e}
# Uses $ssh_control_path to control (i.e. exit)
# Return: local port numeber
sub open_ssh_tunnel () {
    printf "ssh -4 -f -N -M -S $ssh_control_path -L $loc_port:localhost:$opts{e} $opts{l} \n"   if ( exists $opts{D} );
    my $val = system " ssh -4 -f -N -M -S $ssh_control_path -L $loc_port:localhost:$opts{e} $opts{l} ";
    if ( $val != 0 ) {
        die "ERROR: open_ssh_tunnel: ssh returned: $val\n";
    }
}

sub close_ssh_tunnel () {
    printf "close_ssh_tunnel \n"  if ( exists $opts{D} );
    system " ssh -S $ssh_control_path -O exit $opts{l} ";
}
    
    
############### MAIN MAIN MAIN ############################### 
############### MAIN MAIN MAIN ############################### 

get_args();

# open short term tunnel to a tpot
open_ssh_tunnel();

# Grab data from tpots elasticsearch
#   open( ES, "cat /home/baerm/bin/tempes.txt  |" ) ||

if ( exists $opts{v} ) {
    printf  "python3 $ENV{HOME}/bin/es-to-fsdb.py  -p $loc_port $opts{i} -U -B -H -F \"\@timestamp\" -F \"src_ip\" -F \"geoip_asn\" -s $opts{n} -D \'gte:now-${opts{d}}d/d\' -M \"type:Suricata\" -M \"event_type:alert\" -X \"src_ip:8.8.8.8\"  ";
}

open( ES, "python3 $ENV{HOME}/bin/es-to-fsdb.py  -p $loc_port $opts{i} -U -B -H -F \"\@timestamp\" -F \"src_ip\" -F \"geoip_asn\" -s $opts{n} -D \'gte:now-${opts{d}}d/d\' -M \"type:Suricata\" -M \"event_type:alert\" -X \"src_ip:8.8.8.8\"  -o - 2>$error_log |" ) ||
die "$0: Error: unable to open elasticsearch command properly: $!\n";

# save ES results
my @ES_A = <ES>;
close ES;
chomp @ES_A;

# Open Kafka or Standard out
my $KP;
my $KPB;

if ( exists $opts{s} ) {
    $KP = *STDOUT;
}
else {
    if ( exists $opts{k} ) {
        if ( ! open ( $KP, "| $KPATH/kafka-console-producer.sh --broker-list canary.netsec:9091 --topic \"$opts{k}\" ")  ) {
            die "$0: Error: unable to open $KPATH/kafka-console-producer \'$opts{k}\': $!\n";
        }
    }
    if ( ! exists $opts{b} ) {
        if ( ! open ( $KPB, "| $KPATH/kafka-console-producer.sh --broker-list canary.netsec:9091 --topic \"$base_kafka_topic\" ")  ) {
            die "$0: Error: unable to open $KPATH/kafka-console-producer \'$base_kafka_topic\': $!\n";
        }
    }
}

# process elasticsearch results

while ( my $line = shift @ES_A ) {
    if ( exists $opts{D} )  { printf "got %s\n", $line; }
    # catches timestamp ip asn
    # catches timestamp ip
    my $timestamp;
    my $ip;
    my $asn;

    if ( ( $line =~ /^(\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*(\d*)/ ) &&
         ( $line !~ /$RE_FILTER/ ) )
    {
        $timestamp = $1;
        $ip        = $2;
        $asn       = $3;
    }
    # catches timestamp asn ip, because ES, sigh
    elsif  ( ( $line =~ /^(\d+)\s+(\d+)\s+(\d+\.\d+\.\d+\.\d+)/ ) &&
             ( $line !~ /$RE_FILTER/ ) )
    {
        $timestamp = $1;
        $ip        = $3;
        $asn       = $2;
    }
    # else skip line

    # if anything was found
    if ( $timestamp ) {
        my $pri = get_priority($ip);

        if ( $KPB ) {
            printf $KPB "{\"timestamp\": \"%d\", \"value\": \"%s\", \"datatype\": \"ip_address\", \"tag\": \"$opts{t}\", \"other_attributes\": {\"asn\": \"%d\", \"commands_risk\": \"%s\"}}\n", $timestamp, $ip, $asn, $pri;
        }
        if ( $KP ) {
            printf $KP "{\"timestamp\": \"%d\", \"value\": \"%s\", \"datatype\": \"ip_address\", \"tag\": \"$opts{t}\", \"other_attributes\": {\"asn\": \"%d\", \"commands_risk\": \"%s\"}}\n", $timestamp, $ip, $asn, $pri;
        }
    }
}


close $KPB  if ( $KPB );
close $KP   if ( $KP  );
close_ssh_tunnel();
