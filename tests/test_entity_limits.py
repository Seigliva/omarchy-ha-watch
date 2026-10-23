import json
import unittest
from unittest.mock import patch

import bridge
from bridge import Bridge, EntityLimitError


def state(index=0, name='Door', **attrs):
    return {'entity_id': f'binary_sensor.door_{index}', 'state': 'off',
            'attributes': {'friendly_name': name, **attrs}}


class EntityLimits(unittest.TestCase):
    def test_count_boundary_replacement_deletion_and_irrelevant_domains(self):
        b = Bridge()
        for i in range(bridge.ENTITY_COUNT_LIMIT):
            s = state(i)
            b.update_state(s['entity_id'], s)
        self.assertEqual(len(b.states), bridge.ENTITY_COUNT_LIMIT)
        with self.assertRaises(EntityLimitError):
            b.update_state('binary_sensor.extra', {**state(), 'entity_id': 'binary_sensor.extra'})
        b.update_state('binary_sensor.door_0', state(name='Updated'))
        for i in range(3000):
            b.update_state(f'sensor.unused_{i}', {'entity_id': f'sensor.unused_{i}', 'attributes': {'large': 'x' * 1024}})
        self.assertEqual(len(b.states), bridge.ENTITY_COUNT_LIMIT)
        b.update_state('binary_sensor.door_0', None)
        b.update_state('binary_sensor.extra', {**state(), 'entity_id': 'binary_sensor.extra'})
        self.assertEqual(b.state_bytes, sum(b.state_sizes.values()))

    def test_aggregate_exact_boundary_and_rejected_growth_are_atomic(self):
        b = Bridge()
        s = state(name='é' * 256)
        size = len(json.dumps(s | {'attributes': {**s['attributes'], 'device_class': ''}}).encode())
        with patch('bridge.ENTITY_BYTES_LIMIT', size):
            b.update_state(s['entity_id'], s)
            self.assertEqual(b.state_bytes, size)
            with self.assertRaises(EntityLimitError):
                b.update_state(state(1)['entity_id'], state(1))
            self.assertEqual(len(b.states), 1)
        b = Bridge()
        with patch('bridge.ENTITY_BYTES_LIMIT', size - 1):
            with self.assertRaises(EntityLimitError):
                b.load_states([s])
            self.assertFalse(b.states)

    def test_projection_and_field_validation(self):
        b = Bridge()
        s = state(extra=['secret'] * 10000)
        b.load_states([s])
        self.assertNotIn('extra', b.states[s['entity_id']]['attributes'])
        for bad in [state(name='é' * 257), state(name={}), state(device_class=[]),
                    {**state(), 'entity_id': 'binary_sensor.' + 'a' * 256},
                    {**state(), 'state': 'x' * 65}, {**state(), 'attributes': []}]:
            with self.subTest(bad=str(bad)[:80]), self.assertRaises(EntityLimitError):
                b.load_states([bad])
        with self.assertRaises(EntityLimitError):
            b.update_state('binary_sensor.other', state())

    def test_catalog_serialized_limit_before_emit(self):
        b = Bridge()
        b.load_states([state(name='é' * 256)])
        with patch('bridge.emit') as emit:
            b.emit_entities()
            payload = {'type': 'entities', **emit.call_args.kwargs}
            size = len(json.dumps(payload).encode())
            b.entity_catalog = None
            with patch('bridge.CATALOG_BYTES_LIMIT', size):
                b.emit_entities()
            b.entity_catalog = None
            emit.reset_mock()
            with patch('bridge.CATALOG_BYTES_LIMIT', size - 1), self.assertRaises(EntityLimitError):
                b.emit_entities()
            emit.assert_not_called()
            self.assertIsNone(b.entity_catalog)

    def test_initial_snapshot_cannot_bypass_count(self):
        with patch('bridge.ENTITY_COUNT_LIMIT', 2):
            b = Bridge()
            with self.assertRaises(EntityLimitError):
                b.load_states([state(i) for i in range(3)])
            self.assertLessEqual(len(b.states), 2)
