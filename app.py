import os
import ipaddress
import CloudFlare
import waitress
import flask


app = flask.Flask(__name__)


def change_ipv6_prefix(ipv6_address, new_prefix):
    original_ipv6 = ipaddress.IPv6Address(ipv6_address)
    new_prefix_net = ipaddress.IPv6Network(new_prefix, strict=False)
    host_part = int(original_ipv6) & ~int(new_prefix_net.netmask)
    new_ipv6_address = ipaddress.IPv6Address(
        new_prefix_net.network_address + host_part)

    return str(new_ipv6_address)


@app.route('/', methods=['GET'])
def main():
    token = flask.request.args.get('token')
    zone = flask.request.args.get('zone')
    record = flask.request.args.get('record')
    ipv4 = flask.request.args.get('ipv4')
    ipv6 = flask.request.args.get('ipv6')
    ipv6prefix = flask.request.args.get('ipv6prefix')
    cf = CloudFlare.CloudFlare(token=token)

    print(flask.request)
    print(ipv6)
    print(ipv6prefix)

    if not token:
        return flask.jsonify({'status': 'error', 'message': 'Missing token URL parameter.'}), 400
    if not zone:
        return flask.jsonify({'status': 'error', 'message': 'Missing zone URL parameter.'}), 400
    if not ipv4 and not ipv6 and not ipv6prefix:
        return flask.jsonify({'status': 'error', 'message': 'Missing ipv4, ipv6 or ipv6family URL parameter.'}), 400

    try:
        zones = cf.zones.get(params={'name': zone})

        if not zones:
            return flask.jsonify({'status': 'error', 'message': 'Zone {} does not exist.'.format(zone)}), 404

        record_zone_concat = '{}.{}'.format(
            record, zone) if record is not None else zone

        a_record = cf.zones.dns_records.get(zones[0]['id'], params={
                                            'name': record_zone_concat, 'match': 'all', 'type': 'A'})
        aaaa_record = cf.zones.dns_records.get(zones[0]['id'], params={
            'name': record_zone_concat, 'match': 'all', 'type': 'AAAA'})

        if ipv4:
            if not a_record:
                return flask.jsonify({'status': 'error', 'message': f'A record for {record_zone_concat} does not exist.'}), 404
            old_ipv4 = a_record[0]['content']
            if ipv4 != old_ipv4:
                for record in cf.zones.dns_records.get(zones[0]['id'], params={'type': 'A', 'content': old_ipv4}):
                    cf.zones.dns_records.put(
                        zones[0]['id'],
                        record['id'],
                        data={
                            'name': record['name'],
                            'type': 'A',
                            'content': ipv4,
                            'proxied': record['proxied'],
                            'ttl': record['ttl']
                        }
                    )

        if ipv6:
            if not aaaa_record:
                return flask.jsonify({'status': 'error', 'message': f'AAAA record for {record_zone_concat} does not exist.'}), 404
            old_ipv6 = aaaa_record[0]['content']
            if ipv6 != old_ipv6:
                for record in cf.zones.dns_records.get(zones[0]['id'], params={'type': 'AAAA', 'content': old_ipv6}):
                    print("Replacing", record)
                    cf.zones.dns_records.put(
                        zones[0]['id'],
                        record['id'],
                        data={
                            'name': record['name'],
                            'type': 'AAAA',
                            'content': ipv6,
                            'proxied': record['proxied'],
                            'ttl': record['ttl']
                        }
                    )

        if ipv6prefix:
            for record in cf.zones.dns_records.get(zones[0]['id'], params={'type': 'AAAA'}):
                print("Old IP:", record['content'])
                print("Old New IP:", change_ipv6_prefix(
                    record['content'], ipv6prefix))
                print("Record:", record)
                cf.zones.dns_records.put(
                    zones[0]['id'],
                    record['id'],
                    data={
                        'name': record['name'],
                        'type': 'AAAA',
                        'content': change_ipv6_prefix(record['content'], ipv6prefix),
                        'proxied': record['proxied'],
                        'ttl': record['ttl']
                    }
                )

    except CloudFlare.exceptions.CloudFlareAPIError as e:
        return flask.jsonify({'status': 'error', 'message': str(e)}), 500

    return flask.jsonify({'status': 'success', 'message': 'Update successful.'}), 200


@app.route('/healthz', methods=['GET'])
def healthz():
    return flask.jsonify({'status': 'success', 'message': 'OK'}), 200


app.secret_key = os.urandom(24)
waitress.serve(app, host='0.0.0.0', port=80)
