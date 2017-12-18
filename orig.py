nodes = \
{'_condition_0': {'condition': '(valid ipv4)',
                  'num_fields': 0,
                  'type': 'condition'},
 'ipv4_da_lpm_ACTION': {'num_fields': 1, 'type': 'action'},
 'ipv4_da_lpm_MATCH': {'key_width': 32, 'type': 'match'},
 'ipv6_da_exact_ACTION': {'num_fields': 1, 'type': 'action'},
 'ipv6_da_exact_MATCH': {'key_width': 128, 'type': 'match'},
 'mac_da_ACTION': {'num_fields': 4, 'type': 'action'},
 'mac_da_MATCH': {'key_width': 32, 'type': 'match'}}

edges = \
{('_condition_0', 'ipv4_da_lpm_ACTION'): {'condition': True,
                                          'delay': 0,
                                          'dep_type': 'rmt_successor'},
 ('_condition_0', 'ipv6_da_exact_ACTION'): {'condition': False,
                                            'delay': 0,
                                            'dep_type': 'rmt_successor'},
 ('ipv4_da_lpm_ACTION', 'mac_da_MATCH'): {'delay': 1, 'dep_type': 'rmt_match'},
 ('ipv4_da_lpm_MATCH', 'ipv4_da_lpm_ACTION'): {'delay': 9,
                                               'dep_type': 'new_match_to_action'},
 ('ipv6_da_exact_ACTION', 'mac_da_MATCH'): {'delay': 1,
                                            'dep_type': 'rmt_match'},
 ('ipv6_da_exact_MATCH', 'ipv6_da_exact_ACTION'): {'delay': 9,
                                                   'dep_type': 'new_match_to_action'},
 ('mac_da_MATCH', 'mac_da_ACTION'): {'delay': 9,
                                     'dep_type': 'new_match_to_action'}}
