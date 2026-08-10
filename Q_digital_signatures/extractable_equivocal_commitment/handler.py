from eec import server_eec, client_eec
import logging

# Configure logging
#logging.basicConfig(level=logging.INFO)

class ProtocolHandler:
    def __init__(self, dict, inx, reader, writer, role):
        self.dict = dict
        self.inx = inx
        self.reader = reader
        self.writer = writer
        self.role = role  # 'server' or 'client'
        self.result = None

    async def run_protocol(self):
        if self.role == 'server':
            await server_eec(64, self.dict, self.reader, self.writer)            
        else:
            self.result = await client_eec(self.inx, self.reader, self.writer)
            