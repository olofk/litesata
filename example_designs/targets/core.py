from litex.gen.fhdl.specials import Keep
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.build.xilinx.platform import XilinxPlatform

from targets import *

from litesata.common import *
from litesata.phy import LiteSATAPHY
from litesata.core import LiteSATACore
from litesata.frontend.arbitration import LiteSATACrossbar
from litesata.frontend.raid import LiteSATAStriping
from litesata.frontend.bist import LiteSATABIST


_io = [
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 1, Pins(1)),
    ("sata_clocks", 0,
        Subsignal("refclk_p", Pins(1)),
        Subsignal("refclk_n", Pins(1))
    ),
]
for i in range(4):
    _io.append(("sata", i,
                   Subsignal("txp", Pins(1)),
                   Subsignal("txn", Pins(1)),
                   Subsignal("rxp", Pins(1)),
                   Subsignal("rxn", Pins(1))
                )
    )


class CorePlatform(XilinxPlatform):
    name = "core"
    def __init__(self):
        XilinxPlatform.__init__(self, "xc7", _io)

    def do_finalize(self, *args, **kwargs):
        pass


class Core(Module):
    platform = CorePlatform()
    def __init__(self, platform, design="base", clk_freq=200*1000000, nports=2, ports_dw=32):
        self.clk_freq = clk_freq

        if design == "base" or design == "bist":
            # SATA PHY/Core/frontend
            self.submodules.sata_phy = LiteSATAPHY(platform.device, platform.request("sata_clocks"), platform.request("sata"), "sata_gen3", clk_freq)
            self.sata_phys = [self.sata_phy]
            self.submodules.sata_core = LiteSATACore(self.sata_phy)
            self.submodules.sata_crossbar = LiteSATACrossbar(self.sata_core)

            if design == "bist":
                # BIST
                self.submodules.sata_bist = LiteSATABIST(self.sata_crossbar)

            self.specials += [
                Keep(ClockSignal("sata_rx")),
                Keep(ClockSignal("sata_tx"))
            ]

        elif design == "striping":
            self.nphys = 4
            # SATA PHYs
            self.sata_phys = []
            for i in range(self.nphys):
                sata_phy = LiteSATAPHY(platform.device,
                                       platform.request("sata_clocks") if i == 0 else self.sata_phys[0].crg.refclk,
                                       platform.request("sata", i),
                                       "sata_gen3",
                                       clk_freq)
                sata_phy = ClockDomainsRenamer({"sata_rx": "sata_rx{}".format(str(i)),
                                                "sata_tx": "sata_tx{}".format(str(i))})(sata_phy)
                setattr(self.submodules, "sata_phy{}".format(str(i)), sata_phy)
                self.sata_phys.append(sata_phy)

            # SATA Cores
            self.sata_cores = []
            for i in range(self.nphys):
                sata_core = LiteSATACore(self.sata_phys[i])
                setattr(self.submodules, "sata_core{}".format(str(i)), sata_core)
                self.sata_cores.append(sata_core)

            # SATA Frontend
            self.submodules.sata_striping = LiteSATAStriping(self.sata_cores)
            self.submodules.sata_crossbar = LiteSATACrossbar(self.sata_striping)

            for i in range(len(self.sata_phys)):
                self.specials += [
                    Keep(ClockSignal("sata_rx{}".format(str(i)))),
                    Keep(ClockSignal("sata_tx{}".format(str(i))))
                ]

        else:
            ValueError("Unknown design " + design)


        # Get user ports from crossbar
        self.user_ports = self.sata_crossbar.get_ports(nports, ports_dw)

    def get_ios(self):
        ios = set()

        for sata_phy in self.sata_phys:
            # Transceiver
            for e in dir(sata_phy.clock_pads):
                obj = getattr(sata_phy.clock_pads, e)
                if isinstance(obj, Signal):
                    ios = ios.union({obj})
            for e in dir(sata_phy.pads):
                obj = getattr(sata_phy.pads, e)
                if isinstance(obj, Signal):
                    ios = ios.union({obj})

            # Status
            ios = ios.union({
                sata_phy.crg.ready,
                sata_phy.ctrl.ready
            })

        # BIST
        if hasattr(self, "sata_bist"):
            for bist_unit in ["generator", "checker"]:
                for signal in ["start", "sector", "count", "random", "done", "aborted", "errors"]:
                    ios = ios.union({getattr(getattr(self.sata_bist, bist_unit), signal)})
            ios = ios.union({
                self.sata_bist.identify.start,
                self.sata_bist.identify.done,
                self.sata_bist.identify.source.stb,
                self.sata_bist.identify.source.data,
                self.sata_bist.identify.source.ack
            })

        # User ports
        def _iter_layout(layout):
            for e in layout:
                if isinstance(e[1], list):
                    yield from _iter_layout(e[1])
                else:
                    yield e

        for port in self.user_ports:
            for endpoint in [port.sink, port.source]:
                for e in _iter_layout(endpoint.layout):
                    obj = getattr(endpoint, e[0])
                    ios = ios.union({obj})
        return ios

default_subtarget = Core
