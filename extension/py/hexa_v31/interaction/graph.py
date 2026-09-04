from __future__ import annotations

class InteractionGraphError(RuntimeError): pass

def build_interaction_graph(intents:list[dict])->dict:
    nodes={}
    edges=[]
    for row in intents:
        iid=str(row['interaction_id'])
        subject=str(row['subject_event_id'])
        obj=str(row.get('object_event_id') or '')
        result=str(row.get('result_event_id') or '')
        nodes.setdefault(subject,{'node_id':subject,'roles':[]})['roles'].append(iid+':SUBJECT')
        if obj:
            nodes.setdefault(obj,{'node_id':obj,'roles':[]})['roles'].append(iid+':OBJECT')
            edges.append({'from':subject,'to':obj,'interaction_id':iid,'kind':'ACTION_TO_REACTION'})
        if result and result not in {subject,obj}:
            nodes.setdefault(result,{'node_id':result,'roles':[]})['roles'].append(iid+':RESULT')
            edges.append({'from':obj or subject,'to':result,'interaction_id':iid,'kind':'REACTION_TO_CONSEQUENCE'})
    adjacency={k:[] for k in nodes}
    indegree={k:0 for k in nodes}
    for edge in edges:
        a,b=edge['from'],edge['to']
        if a==b:continue
        adjacency.setdefault(a,[]).append(b);indegree[b]=indegree.get(b,0)+1
    queue=sorted(k for k,v in indegree.items() if v==0);order=[]
    while queue:
        n=queue.pop(0);order.append(n)
        for nxt in sorted(adjacency.get(n,[])):
            indegree[nxt]-=1
            if indegree[nxt]==0:
                queue.append(nxt);queue.sort()
    cyclic=sorted(k for k,v in indegree.items() if v>0)
    return {
        'schema':'HEXA_INTERACTION_GRAPH_V2','version':'2.0',
        'nodes':[nodes[k] for k in sorted(nodes)],'edges':edges,
        'topological_order':order,'cycle_node_ids':cyclic,'pass':not cyclic,
    }
