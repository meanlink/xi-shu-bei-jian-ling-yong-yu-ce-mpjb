from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class TransferStatus(str, Enum):
    pending = 'pending'        # 待发
    in_transit = 'in_transit'  # 在途
    partial = 'partial'        # 部分收货
    returning = 'returning'    # 退运在途
    closed = 'closed'          # 结清
