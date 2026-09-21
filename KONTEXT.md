Ändringslogg (uppdatera vid ändringar):
2026-08-08 - Skapad av Emil J

# Råttfällan 

Råttfällan är en mission planner som givet ett uppdrag ska kunna ge förslag på hur det kan genomföras till en ugv-grupp. Syftet är att underlätta för befäl/gruppledare.

## Termer

* Puck - reläsändare
* Råtta - liten UGV
* Operatör - förare av råttan
* Navigatör - planerare under pågående operation, stöd till operatör

## Råttan

Råttan kommer att köras av primärt två personer, en operatör och en navigatör. Operatören ser kamera-feed och styr råttan, navigatören ser en karta och kan lägga upp rutter och synka med ledningssystem som ATAK. Se projekt ratak-ai för operator och navigator vyerna.

Råttan nås via en sändare med begränsad räckvidd och kommer ha möjlighet att släppa efter sig reläsändare för att utöka räckvidden.

## Ratak-ai

Projekt innehållande hela server arkitekturen för att kunna styra råttor. Ska ligga i samma mapp som detta projekt.

## RatMap

Alla kartor hämtas härifrån, samt info från ledningssystem. Ska ligga i samma mapp som detta projekt.

## Algoritm

Algoritmen för hela systemet beskrivs av [pseudocode-v2.md](./pseudocode-v2.md)

### Indata

Indatan består av uppdragsformulering, ett antal parametrar som navigatör eller gruppledare anger samt viss data från ledningssystem.

**Uppdragsformuleringen** ska innehålla följande:

* Mål: Plats dit råttan ska ta sig
* Krav på batteri vid mål: Hur mycket batteri råttan behöver ha kvar för att utföra sitt uppdrag på platsen
* Tidskrav: hur lång tid gruppen har att få råttan till mål

**Anges av grupphef/navigatör**

* Antalet puckar tillgängligt
* Hur nära fienden vi vågar vara

**Från ledningssystem och ratmap**

* senast kända positioner av fienden
* Position av sidoförband
* Andra råttor och deras planerade vägar
* Användarinlagda vägar
* Mineringar/avstängda vägar


### Utdata

Ska ge ett antal förslag på olika sätt att genomföra uppdraget på och utvärdera dem alla genom

* Samband - sannolikhet att kunna nå råttan hela vägen
* Flygskyddstyp (hus, träd)
* Hur lång tid uppdraget tar
* Täckning i området (möjlighet att ha uppkoppling till råttan)
* Fria tillbakaryckningsvägar
* Möjlighet till underhåll
* Beskrivning av väg (skydd, framkomlighet)