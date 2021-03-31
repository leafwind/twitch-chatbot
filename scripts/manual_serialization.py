import dill
from expiringdict import ExpiringDict
with open("data/harnaisxsumire666.bin", "wb") as f:
    data = {"gbf_room_num": 139, "gbf_room_id_cache": ExpiringDict(max_len=1, max_age_seconds=600)}
    data["gbf_room_id_cache"]["user_id"] = "DA3F9600"
    f.write(dill.dumps(data))

import dill
with open("data/harnaisxsumire666.bin", "rb") as f:
    print(dill.loads(f.read()))
