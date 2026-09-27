from engine.core.cpu_affinity import cpus_from_options


def test_cpus_from_cpuset_overrides_mask() -> None:
    cpus = cpus_from_options("0xF", "0,2-3")
    assert cpus == {0, 2, 3}


def test_cpus_from_mask_hex() -> None:
    cpus = cpus_from_options("0x3", None)
    assert cpus == {0, 1}
