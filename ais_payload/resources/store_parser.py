#!/usr/bin/env python2.7
# Parser for SAAM AIS message stores.
# Ref: /air/ais/saam/src/saam-ais-lib/src/ais/store/ais_store.h.
# TODO: Cleanup further, make robust against truncated files,
# and consider migrating to ctypes.

from construct import UBInt8, SBInt8, UBInt16, UBInt32, BFloat32, Enum, \
    Struct, Switch, this, Bytes, GreedyRange, Magic
import subprocess
import binascii
import argparse
import errno
import os
import sys
import logging
import nmea_coder


log = logging.getLogger()

# Enumeration of possible chunk types
CHUNK_TYPE = Enum(UBInt8('type'), CHECKSUM=0, VERSION=1, MSG=2,
                  DEMOD_STATE=3, RUN_STATS=4, DEMOD_CFG=5,
                  DEMOD_VIT_ZS_CFG=6)

# Structure definitions for each CHUNK_TYPE
CHECKSUM_CHUNK = Struct('checksum', UBInt8('C1'), UBInt8('C0'))
VERSION_CHUNK = Struct('version', Bytes('version', this._.nof_data_bytes))
MSG_CHUNK = Struct('msg', UBInt32('time_stamp'), UBInt32('seq_num'),
                   UBInt8('ec_status'), UBInt8('channel'),
                   SBInt8('doppler_zone_num'),
                   UBInt8('rssi'),
                   UBInt8('is_decollided'),
                   Bytes('msg_data', this._.nof_data_bytes - 15),
                   UBInt16('hdlc_crc'))
RUN_STATS_CHUNK = Struct('run_stats',
                         UBInt32('nof_chunks'),
                         UBInt32('nof_input_gaps'),
                         UBInt32('nof_input_proto_failures'),
                         UBInt32('nof_input_timeouts'),
                         UBInt32('nof_discarded_msgs'),
                         UBInt32('nof_collected_msgs'),
                         UBInt32('nof_crc_ok_msgs'),
                         UBInt32('nof_crc_err_msgs'),
                         UBInt32('nof_crc_1bit_msgs'),
                         UBInt32('nof_crc_1x2bit_msgs'),
                         UBInt32('nof_overruns'),
                         BFloat32('max_margin_ratio'),
                         BFloat32('min_margin_ratio'),
                         UBInt32('nof_prio_msgs'),
                         UBInt32('nof_surplus_msgs'),
                         UBInt32('nof_prioritizer_flushes'))
DEMOD_STATE_CHUNK = Struct('demod_state',
                           UBInt32('reference_id'),
                           UBInt32('next_seq_num'))
DEMOD_CFG_CHUNK = Struct('demod_cfg',
                         UBInt32('chunk_nof_raw_words'),
                         UBInt32('sample_rate_hz'),
                         UBInt8('real_valued_samples'),
                         UBInt8('nof_channels'),
                         UBInt8('channels_3_and_4'),
                         UBInt8('nof_doppler_zones'),
                         UBInt16('max_doppler_hz'),
                         Bytes('demod_type', this._.nof_data_bytes - 14))
DEMOD_VIT_ZS_CFG_CHUNK = Struct('demod_vit_zs_cfg',
                                UBInt16('doppler_resolution_hz'))

# Composite chunk type
CHUNK = Struct('chunk',
               CHUNK_TYPE,
               UBInt8('nof_data_bytes'),
               Switch('data', this.type, {
                   'CHECKSUM': CHECKSUM_CHUNK,
                   'VERSION': VERSION_CHUNK,
                   'MSG': MSG_CHUNK,
                   'RUN_STATS': RUN_STATS_CHUNK,
                   'DEMOD_STATE': DEMOD_STATE_CHUNK,
                   'DEMOD_CFG': DEMOD_CFG_CHUNK,
                   'DEMOD_VIT_ZS_CFG': DEMOD_VIT_ZS_CFG_CHUNK}))

# Composite store, consisting of header and a sequence of chunks
STORE = Struct('store', Magic(b'\x5a\xa3\xa1\x50'), GreedyRange(CHUNK))


def fletcher_update(fletcher_state, v):
    fletcher_state[1] = (fletcher_state[1] + v) % 255
    fletcher_state[0] = (fletcher_state[0] + fletcher_state[1]) % 255


def parse(fn):
    if os.path.isfile(fn):
        store = STORE.parse(subprocess.check_output(["xzdec", fn]))
        if not verify_checksums(store):
            raise IOError(errno.ENOENT, "bad header checksums", fn)
        return store
    else:
        raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), fn)


def verify_checksums(parsed_store):
    result = True
    fletcher_state = [0, 0]
    for c in parsed_store['chunk']:
        if c['type'] == 'CHECKSUM':
            act_state = [c['data']['C1'], c['data']['C0']]
            if fletcher_state != act_state:
                log.error('bad checksum %s, expected %s',
                          fletcher_state, act_state)
                result = False

        fletcher_update(fletcher_state,
                        ord(CHUNK_TYPE.build(c['type'])))
        fletcher_update(fletcher_state, c['nof_data_bytes'])
    return result


def each_msg(parsed_store):
    for c in parsed_store['chunk']:
        if c['type'] == 'MSG':
            yield (c['data']['channel'], c['data']['msg_data'])


def each_msg_as_hex(parsed_store):
    for channel, data in each_msg(parsed_store):
        mmsi = ((ord(data[1]) << 22) | (ord(data[2]) << 14) |
                (ord(data[3]) << 6) | (ord(data[4]) >> 2))
        yield channel, binascii.hexlify(data), mmsi


if __name__ == '__main__':
    log.addHandler(logging.StreamHandler(sys.stderr))
    log.level = logging.INFO

    result = 0
    ap = argparse.ArgumentParser()
    ap.add_argument('-d', '--dump-msg', dest='dump_msg', action='store_true',
                    help='Dump messages and channel they was received on')
    ap.add_argument('-N', '--dump-nmea', dest='dump_nmea', action='store_true',
                    help='Dump messages as NMEA AIVDM sentences')
    ap.add_argument('-D', '--dump-all', dest='dump_all', action='store_true',
                    help='Dump entire file')
    ap.add_argument('files', nargs='*', help='Files to dump')
    args = ap.parse_args()

    for fn in args.files:
        try:
            parsed_store = parse(fn)
            if args.dump_msg:
                for channel, msg, mmsi in each_msg_as_hex(parsed_store):
                    print channel, msg, mmsi
            if args.dump_nmea:
                for channel, msg in each_msg(parsed_store):
                    channel_id = chr(channel + ord('A') - 1)
                    print nmea_coder.NMEACoder.nmea_string(channel_id, msg)
            if args.dump_all:
                print parsed_store
        except Exception as e:
            log.error('%s: %s: cannot parse: %s' % (sys.argv[0], fn, str(e)))
            result = 1
    exit(result)
