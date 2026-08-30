import cv2
import numpy as np

from hexa_v31.hierarchy import TopologicalDecompositionValidator, decompose_semantic_group

validator=TopologicalDecompositionValidator()

# Detached, independently readable source components remain a valid exact partition.
root=np.zeros((180,320),np.uint8)
cv2.rectangle(root,(30,45),(120,140),255,-1);cv2.circle(root,(235,92),55,255,-1)
left=np.zeros_like(root);left[:,0:160]=root[:,0:160]
right=np.zeros_like(root);right[:,160:]=root[:,160:]
valid=validator.validate(root,[left,right],'DETACHED_LOBES')
assert valid['pass'] and valid['reconstruction_error']==0 and valid['detached_partition']
result=decompose_semantic_group(root,W=320,H=180,semantic_type='CONCEPT')
assert result['accepted'] and result['topology_validation']['pass']
assert np.array_equal(np.maximum.reduce([c.mask for c in result['children']]),root)
assert any(c.animation_safe for c in result['children'])

# A thin physical connector cannot be converted into an exposed straight cut.
connected=np.zeros_like(root)
cv2.circle(connected,(80,90),52,255,-1);cv2.circle(connected,(240,90),52,255,-1);cv2.rectangle(connected,(80,86),(240,94),255,-1)
a=np.zeros_like(root);a[:,:160]=connected[:,:160]
b=np.zeros_like(root);b[:,160:]=connected[:,160:]
thin=validator.validate(connected,[a,b],'THIN_CONNECTOR_LOBES')
assert not thin['pass'] and 'SKELETON_CONNECTOR_CUT' in thin['reasons']

# Cutting through a branched skeleton loses important topology.
branch=np.zeros_like(root)
cv2.line(branch,(160,25),(160,155),255,9);cv2.line(branch,(70,90),(250,90),255,9)
top=np.zeros_like(root);top[:90,:]=branch[:90,:]
bottom=np.zeros_like(root);bottom[90:,:]=branch[90:,:]
branched=validator.validate(branch,[top,bottom],'THIN_CONNECTOR_LOBES')
assert not branched['pass'] and 'SKELETON_BRANCH_DAMAGE' in branched['reasons']

# A straight internal partition of one connected body is an artificial seam.
body=np.zeros_like(root);cv2.rectangle(body,(55,35),(265,145),255,-1)
p=np.zeros_like(root);p[:,:160]=body[:,:160]
q=np.zeros_like(root);q[:,160:]=body[:,160:]
seam=validator.validate(body,[p,q],'COLOR_GEOMETRIC_WATERSHED')
assert not seam['pass'] and 'ARTIFICIAL_EXPOSED_SEAM' in seam['reasons']

# Uncertain connected shapes remain atomic.
uncertain=np.zeros_like(root);cv2.circle(uncertain,(160,90),65,255,-1)
fallback=decompose_semantic_group(uncertain,W=320,H=180,semantic_type='CONCEPT')
assert not fallback['accepted'] and not fallback['children']

print('V31_TOPOLOGICAL_DECOMPOSITION_VALIDATOR_PASS')
