
# Elasticsearch Tools / ES to Kafka stream Creation Files

## ES Tools

* ES-to-ES.py : Copy elasticsearch indexes from one ES cluster to another. Allows regex search.
* tpot-ES-to-ES.py : Copy tpot specific indexes from T-Pot ES to another ES cluster.
* es-to-fsdb.py : Query an ES cluster and return data in FSDB format.

## ES Kafka Tools

* tpotcmds-to-kafka :	Copies Cowrie command data to Kafka feed.
* tpot-to-kafka-formatted.pl : Extracts Malicious IP addresses from various Tpot servers and loads 1+ kafka streams with it.
* tpot-to-kafka-formatted.pl : Uses es-to-fsdb.py to pull ES data (bad IPs) from T-Pots, reformats them to a JSON stream, and pushes them into a Kafka server.
* tpots-cumulative-kafka.py : Creates cumulative statistics on the existing Tpot streams over a time window (default: 1 day)
* esdata : Retrieves data from Elasticsearch, targeted toward Tpot ES data.
* gawseed-wrapper : This script is a wrapper around Gawseed commands. It runs a user-specified command line a specified number of times.


# License

Copyright (c) 2021, Parsons, Corp.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

*  Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.

*  Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

*  Neither the name of Parsons, Corp nor the names of its contributors may
   be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS ``AS
IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT
HOLDERS OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
