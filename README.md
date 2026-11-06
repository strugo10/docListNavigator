# Nawigator List i Cyfr Rzymskich (docListNavigator) dla NVDA

Dodatek do czytnika ekranu NVDA dedykowany do pracy z dokumentami w programach **Microsoft Word** oraz **Adobe Acrobat Reader**.

---

## 🎯 Główne funkcjonalności

1. **Hierarchiczna nawigacja po wielopoziomowych listach:**
   - Rozwiązuje problem rozsypanych lub symulowanych list w dokumentach urzędowych, regulaminach i aktach prawnych (ustępy `1.`, punkty `1)`, litery `a)`, tirety `-`).
   - Pozwala skakać pomiędzy punktami na tym samym poziomie (`NVDA + Alt + Strzałka w dół/górę`), do elementu nadrzędnego (`NVDA + Alt + Strzałka w lewo`) oraz do pierwszego podpunktu (`NVDA + Alt + Strzałka w prawo`).
   - Podaje pełną ścieżkę pozycji (`NVDA + Alt + L`): np. *Rozdział VI > ustęp 1 > punkt 1) > litera a)* (dwukrotne wciśnięcie kopiuje do schowka).
   - Otwiera okno drzewa struktury dokumentu (`NVDA + Alt + F7`) z natychmiastową wyszukiwarką i przejściem na klawiszu Enter.

2. **Automatyczna, naturalna wymowa cyfr rzymskich:**
   - NVDA wymawia oznaczenia cyfrowe w systemie rzymskim (np. `III`, `IV`, `VI`, `IX`) jako: *„rzymskie trzy”*, *„rzymskie cztery”*, *„w module rzymskie dwa”*, *„Rozdział rzymskie sześć”*.
   - Inteligentny filtr chroni zwykły polski spójnik *„i”* (np. *„Jan i Maria”* nie ulega zmianie).

---

## ⌨️ Tabela skrótów klawiszowych

| Skrót | Działanie |
|---|---|
| `NVDA + Alt + L` | Odczytanie pełnej ścieżki hierarchicznej (dwukrotne wciśnięcie kopiuje do schowka) |
| `NVDA + Alt + Strzałka w dół` | Skok do następnego punktu na tym samym poziomie logicznym |
| `NVDA + Alt + Strzałka w górę` | Skok do poprzedniego punktu na tym samym poziomie logicznym |
| `NVDA + Alt + Strzałka w lewo` | Skok do elementu nadrzędnego (poziom wyżej) |
| `NVDA + Alt + Strzałka w prawo` | Skok do pierwszego podpunktu (poziom niżej) |
| `NVDA + Alt + F7` | Okno drzewa struktury dokumentu z wyszukiwarką |
| `NVDA + Ctrl + Shift + L` | Przełączenie automatycznego ogłaszania zmiany poziomów przy czytaniu |
| `NVDA + Ctrl + Shift + R` | Przełączenie wymowy cyfr rzymskich |
| `NVDA + Ctrl + Shift + H` | Pomoc podręczna w buforze przeglądania |
| `F1` | Pomoc kontekstowa w oknach dialogowych |

---

## 🛠️ Instalacja i konfiguracja

- Plik pakietu instalacyjnego: `Pakiety_Instalacyjne/docListNavigator.nvda-addon`
- Konfiguracja w NVDA: `Preferencje -> Ustawienia -> Kategoria: Nawigator list i cyfr rzymskich`
