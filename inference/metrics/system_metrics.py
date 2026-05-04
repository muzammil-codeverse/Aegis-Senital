class SystemMetrics:
    def __init__(self):
        self.frames_processed = 0
        self.frames_dropped = 0
        self.queue_overflows = 0
        self.avg_latency_ms = 0
        self.max_latency_ms = 0
        self.circuit_breaker_trips = 0
        self.id_switches = 0

    def to_dict(self):
        return self.__dict__
