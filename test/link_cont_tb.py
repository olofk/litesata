from litesata.common import *
from litesata.core.link import LiteSATACONTInserter, LiteSATACONTRemover

from test.common import *


class ContPacket(list):
    def __init__(self, data=[]):
        self.ongoing = False
        self.done = False
        for d in data:
            self.append(d)


class ContStreamer(PacketStreamer):
    def __init__(self):
        PacketStreamer.__init__(self, phy_description(32), ContPacket)

    def do_simulation(self, selfp):
        PacketStreamer.do_simulation(self, selfp)
        selfp.source.charisk = 0
        # Note: for simplicity we generate charisk by detecting
        # primitives in data
        for k, v in primitives.items():
            try:
                if self.source_data == v:
                    selfp.source.charisk = 0b0001
            except:
                pass


class ContLogger(PacketLogger):
    def __init__(self):
        PacketLogger.__init__(self, phy_description(32), ContPacket)


class TB(Module):
    def __init__(self):
        self.submodules.streamer = ContStreamer()
        self.submodules.streamer_randomizer = Randomizer(phy_description(32), level=50)
        self.submodules.inserter = LiteSATACONTInserter(phy_description(32))
        self.submodules.remover = LiteSATACONTRemover(phy_description(32))
        self.submodules.logger_randomizer = Randomizer(phy_description(32), level=50)
        self.submodules.logger = ContLogger()

        self.submodules.pipeline = Pipeline(
            self.streamer,
            self.streamer_randomizer,
            self.inserter,
            self.remover,
            self.logger_randomizer,
            self.logger
        )

    def gen_simulation(self, selfp):
        test_packet = ContPacket([
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["ALIGN"],
            primitives["ALIGN"],
            primitives["SYNC"],
            primitives["SYNC"],
            #primitives["SYNC"],
            0x00000000,
            0x00000001,
            0x00000002,
            0x00000003,
            0x00000004,
            0x00000005,
            0x00000006,
            0x00000007,
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["ALIGN"],
            primitives["ALIGN"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"],
            primitives["SYNC"]]*4
            )
        streamer_packet = ContPacket(test_packet)
        yield from self.streamer.send(streamer_packet)
        yield from self.logger.receive(len(test_packet))
        #for d in self.logger.packet:
        #    print("{:08}".format(d))

        # check results
        s, l, e = check(streamer_packet, self.logger.packet)
        print("shift " + str(s) + " / length " + str(l) + " / errors " + str(e))


if __name__ == "__main__":
    run_simulation(TB(), ncycles=1024, vcd_name="my.vcd", keep_files=True)
