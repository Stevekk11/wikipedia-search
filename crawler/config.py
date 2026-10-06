"""
Configuration constants and heuristic rules for the Wikipedia Crawler.
"""

from typing import List, Set

from typing import List

DISALLOWED_PREFIXES: List[str] = [
    # -------------------------------------------------------------
    # Canonical / English (valid as universal alias across all wikis)
    # -------------------------------------------------------------
    "Media:",
    "Special:",
    "Talk:",
    "User:",
    "User_talk:",
    "Wikipedia:",
    "Wikipedia_talk:",
    "File:",
    "File_talk:",
    "MediaWiki:",
    "MediaWiki_talk:",
    "Template:",
    "Template_talk:",
    "Help:",
    "Help_talk:",
    "Category:",
    "Category_talk:",
    "Portal:",
    "Portál:",
    "Portal_talk:",
    "Draft:",
    "Draft_talk:",
    "TimedText:",
    "TimedText_talk:",
    "Module:",
    "Module_talk:",
    "Gadget:",
    "Gadget_talk:",
    "Gadget_definition:",
    "Gadget_definition_talk:",
    "Topic:",
    "Book:",
    "Book_talk:",
    # -------------------------------------------------------------
    # Romance (French, Spanish, Italian, Portuguese, Romanian, Catalan)
    # -------------------------------------------------------------
    # User / Talk
    "Utilisateur:",
    "Discussion_utilisateur:",
    "Usuario:",
    "Discusión_usuario:",
    "Utente:",
    "Discussioni_utente:",
    "Utilizador:",
    "Discussão_utilizador:",
    "Usuário:",
    "Discussão_usuário:",  # pt-BR alias
    "Usuari:",
    "Discussió_usuari:",
    "Utilizator:",
    "Discuție_Utilizator:",
    # General Talk
    "Discussion:",
    "Discusión:",
    "Discussione:",
    "Discussioni:",
    "Discussão:",
    "Discussió:",
    "Discuție:",
    # Project / Wikipedia
    "Wikipédia:",
    "Discussion_Wikipédia:",
    "Discusión_Wikipedia:",
    "Discussioni_Wikipedia:",
    "Discussão_Wikipédia:",
    "Discussió_Wikipedia:",
    "Discuție_Wikipedia:",
    # File
    "Fichier:",
    "Discussion_fichier:",
    "Archivo:",
    "Discusión_archivo:",
    "Imagen:",
    "Immagine:",
    "Discussioni_file:",
    "Ficheiro:",
    "Discussão_ficheiro:",
    "Imagem:",
    "Fitxer:",
    "Discussió_fitxer:",
    "Fișier:",
    "Discuție_Fișier:",
    # Template
    "Modèle:",
    "Discussion_modèle:",
    "Plantilla:",
    "Discusión_plantilla:",
    "Modello:",
    "Discussioni_template:",
    "Predefinição:",
    "Discussão_predefinição:",
    "Plantilla:",
    "Discussió_plantilla:",
    "Format:",
    "Discuție_Format:",
    # Category
    "Catégorie:",
    "Discussion_catégorie:",
    "Categoría:",
    "Discusión_categoría:",
    "Categoria:",
    "Discussioni_categoria:",
    "Discussão_categoria:",
    "Discussió_categoria:",
    "Categorie:",
    "Discuție_Categorie:",
    # Help
    "Aide:",
    "Discussion_aide:",
    "Ayuda:",
    "Discusión_ayuda:",
    "Aiuto:",
    "Discussioni_aiuto:",
    "Ajuda:",
    "Discussão_ajuda:",
    "Ajutor:",
    "Discuție_Ajutor:",
    # Portals, Drafts & Modules
    "Portail:",
    "Discussion_portail:",
    "Portail_talk:",
    "Progetto:",
    "Discussioni_progetto:",
    "Brouillon:",
    "Discussion_brouillon:",
    "Esborrany:",
    "Módulo:",
    "Discussão_módulo:",
    "Discusión_módulo:",
    "Discussioni_modulo:",
    # Special
    "Spécial:",
    "Especial:",
    "Speciale:",
    # -------------------------------------------------------------
    # Germanic (German, Dutch, Swedish, Danish, Norwegian)
    # -------------------------------------------------------------
    # User / Talk
    "Benutzer:",
    "Benutzer_Diskussion:",
    "Gebruiker:",
    "Overleg_gebruiker:",
    "Användare:",
    "Användardiskussion:",
    "Bruker:",
    "Brukerdiskusjon:",
    "Bruger:",
    "Brugerdiskussion:",
    # General Talk
    "Diskussion:",
    "Overleg:",
    "Diskussion:",
    "Diskusjon:",
    # File
    "Datei:",
    "Datei_Diskussion:",
    "Bestand:",
    "Overleg_bestand:",
    "Fil:",
    "Fildiskussion:",
    "Bilde:",
    "Billed:",
    # Template
    "Vorlage:",
    "Vorlage_Diskussion:",
    "Sjabloon:",
    "Overleg_sjabloon:",
    "Mall:",
    "Malldiskussion:",
    "Mal:",
    # Category
    "Kategorie:",
    "Kategorie_Diskussion:",
    "Categorie:",
    "Overleg_categorie:",
    "Kategori:",
    "Kategoridiskussion:",
    # Help
    "Hilfe:",
    "Hilfe_Diskussion:",
    "Hjälp:",
    "Hjälpdiskussion:",
    "Hjelp:",
    # Modules & Portals
    "Modul:",
    "Modul_Diskussion:",
    "Portaal:",
    "Overleg_portaal:",
    # Special
    "Spezial:",
    "Speciaal:",
    "Special:",
    "Spesial:",
    # -------------------------------------------------------------
    # Slavic - Cyrillic (Russian, Ukrainian, Belarusian, Bulgarian, Serbian/Macedonian)
    # -------------------------------------------------------------
    # User
    "Участник:",
    "Обсуждение_участника:",
    "Користувач:",
    "Обговорення_користувача:",
    "Удзельнік:",
    "Размовы_з_удзельнікам:",
    "Потребител:",
    "Потребител_беседа:",
    "Корисник:",
    "Разговор_са_корисником:",
    "Разговор_со_корисник:",
    # General Talk
    "Обсуждение:",
    "Обговорення:",
    "Размовы:",
    "Беседа:",
    "Разговор:",
    # File
    "Файл:",
    "Обсуждение_файла:",
    "Обговорення_файлу:",
    "Изображение:",
    "Слика:",
    # Template
    "Шаблон:",
    "Обсуждение_шаблона:",
    "Обговорення_шаблону:",
    # Category
    "Категория:",
    "Обсуждение_категории:",
    "Категорія:",
    "Обговорення_категорії:",
    "Катэгорыя:",
    # Help
    "Справка:",
    "Обсуждение_справки:",
    "Довідка:",
    "Обговорення_довідки:",
    "Даведка:",
    "Помощ:",
    "Помоћ:",
    # Portals, Modules & Special
    "Портал:",
    "Обсуждение_портала:",
    "Модуль:",
    "Обсуждение_модуля:",
    "Служебная:",
    "Спеціальна:",
    "Адмысловае:",
    "Специални:",
    "Посебно:",
    # -------------------------------------------------------------
    # Slavic - Latin (Polish, Czech, Slovak, Croatian, Bosnian, Slovene)
    # -------------------------------------------------------------
    # User
    "Wikipedysta:",
    "Dyskusja_wikipedysty:",
    "Użytkownik:",
    "Uživatel:",
    "Diskuse_s_uživatelem:",
    "Redaktor:",
    "Diskusia_s_redaktorom:",
    "Uporabnik:",
    "Pogovor_z_uporabnikom:",
    # General Talk
    "Dyskusja:",
    "Diskuse:",
    "Diskusia:",
    "Pogovor:",
    "Razgovor:",
    # File
    "Plik:",
    "Dyskusja_pliku:",
    "Grafika:",
    "Soubor:",
    "Súbor:",
    "Slika:",
    # Template
    "Szablon:",
    "Dyskusja_szablonu:",
    "Šablona:",
    "Šablóna:",
    "Predloga:",
    # Category
    "Kategoria:",
    "Dyskusja_kategorii:",
    "Kategorie:",
    "Kategória:",
    # Help
    "Pomoc:",
    "Dyskusja_pomocy:",
    "Nápověda:",
    "Pomoč:",
    # Special
    "Specjalna:",
    "Speciální:",
    "Špeciálne:",
    "Posebno:",
    # -------------------------------------------------------------
    # Finno-Ugric & Baltic (Finnish, Hungarian, Estonian, Latvian, Lithuanian)
    # -------------------------------------------------------------
    # Finnish / Estonian / Hungarian
    "Käyttäjä:",
    "Keskustelu_käyttäjästä:",
    "Keskustelu:",
    "Tiedosto:",
    "Malline:",
    "Luokka:",
    "Ohje:",
    "Toiminnot:",
    "Kasutaja:",
    "Kasutaja_arutelu:",
    "Arutelu:",
    "Pilt:",
    "Mall:",
    "Kategooria:",
    "Juhend:",
    "Eri:",
    "Szerkesztő:",
    "Szerkesztővita:",
    "Vita:",
    "Kép:",
    "Fájl:",
    "Sablon:",
    "Kategória:",
    "Útmutató:",
    "Speciális:",
    # Baltic (Lithuanian, Latvian)
    "Naudotojas:",
    "Naudotojo_aptarimas:",
    "Aptarimas:",
    "Vaizdas:",
    "Šablonas:",
    "Kategorija:",
    "Pagalba:",
    "Specialus:",
    "Dalībnieks:",
    "Dalībnieka_diskusija:",
    "Diskusija:",
    "Attēls:",
    "Veidne:",
    "Palīdzība:",
    # -------------------------------------------------------------
    # Greek
    # -------------------------------------------------------------
    "Χρήστης:",
    "Συζήτηση_χρήστη:",
    "Συζήτηση:",
    "Βικιπαίδεια:",
    "Αρχείο:",
    "Πρότυπο:",
    "Κατηγορία:",
    "Βοήθεια:",
    "Πύλη:",
    "Module:",
    "Ειδικό:",
    # -------------------------------------------------------------
    # Celtic (Irish, Welsh, Scottish Gaelic)
    # -------------------------------------------------------------
    "Úsáideoir:",
    "Plé_úsáideora:",
    "Plé:",
    "Vicipéid:",
    "Íomhá:",
    "Teimpléad:",
    "Catagóir:",
    "Cabhair:",
    "Speisialta:",
    "Defnyddiwr:",
    "Sgwrs_Defnyddiwr:",
    "Sgwrs:",
    "Wicipedia:",
    "Delwedd:",
    "Nodyn:",
    "Categori:",
    "Cymorth:",
    "Arbennig:",
]

# High-centrality connector hubs that span broad subjects in Wikipedia
HIGH_CENTRALITY_HUBS: Set[str] = {
    "united_states", "united_kingdom", "europe", "north_america", "asia", "africa",
    "world", "earth", "country", "city", "history", "geography", "government",
    "economy", "culture", "society", "human", "biology", "science", "technology",
    "medicine", "law", "philosophy", "psychology", "politics", "education",
    "demographics_of_the_united_states", "human_sexuality", "culture_of_the_united_states", "south_america"
}

# Inverted hub weighting: boost hubs on early hops, penalize them on later hops
HUB_BOOST_MAX_DEPTH: int = 2
HUB_EARLY_BONUS: float = 60.0
HUB_LATE_PENALTY: float = 50.0

# Narrow, dead-end patterns to penalize
DEAD_END_PATTERNS: List[str] = [
    "road", "highway", "state_road", "interstate", "route", "airport",
    "railway", "station", "school", "high_school", "elementary", "middle_school",
    "district", "season", "championship", "tournament", "cup", "election"
]

# Prefixes for index/timeline pages to penalize
INDEX_PREFIXES: List[str] = ["list_of", "timeline_of"]

# Default crawler settings and limits
DEFAULT_USER_AGENT = "WikiHopPathfinder/2.0 (WikipediaHopExplorer; https://localhost:8005; wikihop-crawler@edu.local)"
DEFAULT_REST_USER_AGENT = "WikiHopPathfinder/2.0 (WikipediaHopExplorer; https://localhost:8005; wikihop-crawler@edu.local)"
