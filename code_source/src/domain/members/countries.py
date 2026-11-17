"""Country and nationality of a member, as ISO 3166-1 alpha-2 codes for the FFME CSV export (issue #117).

HelloAsso asks both as free text ("France", "Française", "FRANCAISE"…). A value is recognised only when it is exactly,
case and accents aside, one of the spellings of a country of COUNTRIES: its names, its adjectives (masculine,
feminine, plural), its ISO codes. Nothing is guessed from part of the text (« Afrique du Sud » is not France): a value
that is not recognised gets `None`, and the export lists the member for the office to correct the record.

The member form offers the `name` and `nationality` of each country; adding a country is one line here.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.utils import normalize_name


@dataclass(frozen=True)
class Country:
    code: str  # ISO 3166-1 alpha-2: the "pays" / "nationalite" code of the FFME CSV
    alpha3: str  # ISO 3166-1 alpha-3, accepted when typed
    name: str  # French name, stored by the member form
    nationality: str  # feminine adjective, stored by the member form (most stored values are "Française")
    masculine: str  # masculine adjective
    other_names: tuple[str, ...] = ()


FRANCE_CODE = "FR"

COUNTRIES: tuple[Country, ...] = (
    Country("FR", "FRA", "France", "Française", "Français"),
    Country("ZA", "ZAF", "Afrique du Sud", "Sud-africaine", "Sud-africain"),
    Country("DZ", "DZA", "Algérie", "Algérienne", "Algérien"),
    Country("DE", "DEU", "Allemagne", "Allemande", "Allemand"),
    Country("AD", "AND", "Andorre", "Andorrane", "Andorran"),
    Country("AR", "ARG", "Argentine", "Argentine", "Argentin"),
    Country("AU", "AUS", "Australie", "Australienne", "Australien"),
    Country("AT", "AUT", "Autriche", "Autrichienne", "Autrichien"),
    Country("BE", "BEL", "Belgique", "Belge", "Belge"),
    Country("BR", "BRA", "Brésil", "Brésilienne", "Brésilien"),
    Country("BG", "BGR", "Bulgarie", "Bulgare", "Bulgare"),
    Country("CA", "CAN", "Canada", "Canadienne", "Canadien"),
    Country("CL", "CHL", "Chili", "Chilienne", "Chilien"),
    Country("CN", "CHN", "Chine", "Chinoise", "Chinois"),
    Country("CI", "CIV", "Côte d'Ivoire", "Ivoirienne", "Ivoirien"),
    Country("HR", "HRV", "Croatie", "Croate", "Croate"),
    Country("DK", "DNK", "Danemark", "Danoise", "Danois"),
    Country("ES", "ESP", "Espagne", "Espagnole", "Espagnol"),
    Country("US", "USA", "États-Unis", "Américaine", "Américain", ("Etats-Unis d'Amérique", "États-Unis d'Amérique")),
    Country("FI", "FIN", "Finlande", "Finlandaise", "Finlandais"),
    Country("GR", "GRC", "Grèce", "Grecque", "Grec"),
    Country("HU", "HUN", "Hongrie", "Hongroise", "Hongrois"),
    Country("IN", "IND", "Inde", "Indienne", "Indien"),
    Country("IE", "IRL", "Irlande", "Irlandaise", "Irlandais"),
    Country("IT", "ITA", "Italie", "Italienne", "Italien"),
    Country("JP", "JPN", "Japon", "Japonaise", "Japonais"),
    Country("LU", "LUX", "Luxembourg", "Luxembourgeoise", "Luxembourgeois"),
    Country("MA", "MAR", "Maroc", "Marocaine", "Marocain"),
    Country("MX", "MEX", "Mexique", "Mexicaine", "Mexicain"),
    Country("MC", "MCO", "Monaco", "Monégasque", "Monégasque"),
    Country("NO", "NOR", "Norvège", "Norvégienne", "Norvégien"),
    Country("NZ", "NZL", "Nouvelle-Zélande", "Néo-zélandaise", "Néo-zélandais"),
    Country("NL", "NLD", "Pays-Bas", "Néerlandaise", "Néerlandais", ("Hollande",)),
    Country("PL", "POL", "Pologne", "Polonaise", "Polonais"),
    Country("PT", "PRT", "Portugal", "Portugaise", "Portugais"),
    Country("RO", "ROU", "Roumanie", "Roumaine", "Roumain"),
    Country("GB", "GBR", "Royaume-Uni", "Britannique", "Britannique", ("Grande-Bretagne",)),
    Country("RU", "RUS", "Russie", "Russe", "Russe"),
    Country("SN", "SEN", "Sénégal", "Sénégalaise", "Sénégalais"),
    Country("SE", "SWE", "Suède", "Suédoise", "Suédois"),
    Country("CH", "CHE", "Suisse", "Suisse", "Suisse"),
    Country("CZ", "CZE", "Tchéquie", "Tchèque", "Tchèque", ("République tchèque",)),
    Country("TN", "TUN", "Tunisie", "Tunisienne", "Tunisien"),
    Country("TR", "TUR", "Turquie", "Turque", "Turc"),
    Country("UA", "UKR", "Ukraine", "Ukrainienne", "Ukrainien"),
    Country("VN", "VNM", "Vietnam", "Vietnamienne", "Vietnamien", ("Viêt Nam",)),
)


def _key(value: object) -> str:
    """Case, accents, hyphens and repeated spaces aside: "Royaume-Uni" and " royaume uni " give the same key."""
    return normalize_name(str(value).replace("’", "'"))


def _spellings(country: Country) -> list[str]:
    adjectives = [country.nationality, country.masculine]
    plurals = [adjective + "s" for adjective in adjectives if not adjective.endswith("s")]
    return [country.code, country.alpha3, country.name, *country.other_names, *adjectives, *plurals]


_BY_SPELLING: dict[str, Country] = {_key(spelling): country for country in COUNTRIES for spelling in _spellings(country)}


def parse_country(raw: object) -> Country | None:
    """The country a stored country or nationality designates ("France", "française", "FR", "FRA"…).

    `None` when the value is empty or not recognised: the caller tells them apart (an empty value is not an error)."""
    if raw is None:
        return None
    return _BY_SPELLING.get(_key(raw))


def country_names() -> list[str]:
    """The country names the member form offers, France first."""
    return [country.name for country in COUNTRIES]


def nationality_names() -> list[str]:
    """The nationalities the member form offers, French first."""
    return [country.nationality for country in COUNTRIES]
