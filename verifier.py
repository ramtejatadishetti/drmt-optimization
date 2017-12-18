import sys
import importlib
import json
import math

def verify_schedule(nodes, edges, time_of_op, hw_spec, latency_spec, proc_count):
    
    # iterate over nodes whether evrey node has been allocated a timeslot
    for node in nodes:
        if node not in time_of_op:
            print("Node " + node + "not found")
            return False
    
    # validate dependency constraints
    for edge_tuple in edges:
        if (edge_tuple[0] in nodes) & (edge_tuple[1] in nodes):
            dep_type = edges[(edge_tuple[0], edge_tuple[1])]['dep_type']
            flag = 1
            #print(time_of_op[edge_tuple[0]], time_of_op[edge_tuple[1]], latency_spec.dM, latency_spec.dS, latency_spec.dA )
            if (dep_type == 'new_match_to_action') or (dep_type == 'new_successor_conditional_on_table_result_action_type'):
              # minimum match latency
                if  ( ( time_of_op[edge_tuple[1]] - time_of_op[edge_tuple[0]] ) >= latency_spec.dM) :
                   flag = 0
            
            if (dep_type == 'rmt_reverse_read') or (dep_type == 'rmt_successor'):
              # latency of dS
                if  ( ( time_of_op[edge_tuple[1]] - time_of_op[edge_tuple[0]] ) >= latency_spec.dS) :
                   flag = 0
            
            if (dep_type == 'rmt_action') or (dep_type == 'rmt_match'):
              # minimum action latency
                if  ( ( time_of_op[edge_tuple[1]] - time_of_op[edge_tuple[0]] ) >= latency_spec.dA) :
                   flag = 0
            
            if flag == 1 :
                print("Dependency not met between " + edge_tuple[0] + ", " + edge_tuple[1] )
                return False
    
   # compute per time slot statistics

    match_key_usage = dict()
    action_fields_usage = dict()
    match_units_usage = dict()
    match_proc_set = dict()
    match_proc_usage = dict()
    action_proc_set = dict()
    action_proc_usage = dict()

    for t in range(proc_count):
        match_key_usage[t] = 0
        action_fields_usage[t] = 0
        match_units_usage[t]   = 0
        match_proc_set[t]      = set()
        match_proc_usage[t]    = 0
        action_proc_set[t]     = set()
        action_proc_usage[t]   = 0

    for v in nodes:
        k = time_of_op[v] / proc_count
        r = time_of_op[v] % proc_count

        if nodes[v]['type'] == 'match':
            match_key_usage[r] += nodes[v]['key_width']
            match_units_usage[r] += math.ceil((1.0 * nodes[v]['key_width'])/ hw_spec.match_unit_size)
            match_proc_set[r].add(k)
            match_proc_usage[r] = len(match_proc_set[r])
        
        else:
            action_fields_usage[r] += nodes[v]['num_fields']
            action_proc_set[r].add(k)
            action_proc_usage[r] = len(action_proc_set[r])
    
    # validate ipc and resource constarints
    for t in range(proc_count):
        if match_units_usage[t] > hw_spec.match_unit_limit :
            print("Match utilization failed in"  + str(t) + " slot" )
            return False

        if match_proc_usage[t] > hw_spec.match_proc_limit :
            print("Match ipc failed in"  + str(t) + " slot" )
            return False

        if action_fields_usage[t] > hw_spec.action_fields_limit :
            print("Action utilization failed in " + str(t) + " slot")
            return False

        if action_proc_usage[t] > hw_spec.action_proc_limit :
            print("Action ipc failed in"  + str(t) + " slot" )
            return False

    return True


if __name__ == "__main__" :
    if (len(sys.argv) <= 4 ) :
        print("Usage: ", sys.argv[0], "<DAG_file> <HW_file> <LT_file> <JSON_file> ")
        exit(1)
    else :
        input_graph = importlib.import_module(sys.argv[1], "*")
        hw_spec = importlib.import_module(sys.argv[2], "*")
        latency_spec = importlib.import_module(sys.argv[3], "*")
        json_file = sys.argv[4]
    

    with open(json_file) as data_file: 
        json_data = json.load(data_file)

    time_of_op = json_data['time_of_op']
    proc_count = json_data['proc_count']

    if verify_schedule(input_graph.nodes, input_graph.edges, time_of_op, hw_spec, latency_spec, proc_count) == True:
        print('Solution is correct')
    else:
        print('Solution is incorrect')
    