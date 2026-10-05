"""Owner-supplied domain registry. Stable IDs retain existing foreign keys."""

from typing import TypedDict


class Institution(TypedDict):
    id: int
    name: str
    shortName: str
    studentEmailDomain: str
    isActive: bool


def entry(id: int, name: str, short: str, domain: str) -> Institution:
    return {
        "id": id,
        "name": name,
        "shortName": short,
        "studentEmailDomain": domain,
        "isActive": True,
    }


INSTITUTIONS: tuple[Institution, ...] = (
    entry(1, "Cape Peninsula University of Technology", "CPUT", "mycput.ac.za"),
    entry(2, "Central University of Technology", "CUT", "cut.ac.za"),
    entry(3, "Durban University of Technology", "DUT", "dut4life.ac.za"),
    entry(4, "Mangosuthu University of Technology", "MUT", "mut.ac.za"),
    entry(5, "Nelson Mandela University", "NMU", "mandela.ac.za"),
    entry(6, "North-West University", "NWU", "nwu.ac.za"),
    entry(7, "Rhodes University", "RU", "ru.ac.za"),
    entry(8, "Sefako Makgatho Health Sciences University", "SMU", "smu.ac.za"),
    entry(9, "Sol Plaatje University", "SPU", "spu.ac.za"),
    entry(10, "Stellenbosch University", "SU", "sun.ac.za"),
    entry(11, "Tshwane University of Technology", "TUT", "tut4life.ac.za"),
    entry(12, "University of South Africa", "UNISA", "mylife.unisa.ac.za"),
    entry(13, "University of the Free State", "UFS", "ufs.ac.za"),
    entry(14, "University of Cape Town", "UCT", "uct.ac.za"),
    entry(15, "University of Fort Hare", "UFH", "ufh.ac.za"),
    entry(16, "University of Johannesburg", "UJ", "uj.ac.za"),
    entry(17, "University of KwaZulu-Natal", "UKZN", "ukzn.ac.za"),
    entry(18, "University of Limpopo", "UL", "ul.ac.za"),
    entry(19, "University of Mpumalanga", "UMP", "ump.ac.za"),
    entry(20, "University of Pretoria", "UP", "tuks.co.za"),
    entry(21, "University of the Western Cape", "UWC", "uwc.ac.za"),
    entry(22, "University of the Witwatersrand", "WITS", "students.wits.ac.za"),
    entry(23, "University of Venda", "UNIVEN", "univen.ac.za"),
    entry(24, "University of Zululand", "UNIZULU", "unizulu.ac.za"),
    entry(25, "Vaal University of Technology", "VUT", "vut.ac.za"),
    entry(26, "Walter Sisulu University", "WSU", "wsu.ac.za"),
)
DUT_ID = next(i["id"] for i in INSTITUTIONS if i["shortName"] == "DUT")
ADMIN_EMAIL = "22445780@" + next(i["studentEmailDomain"] for i in INSTITUTIONS if i["id"] == DUT_ID)
