# Codefon – Home Assistant integráció

A Codefon kaputelefonra kötött Codefon naplózó készülék Home Assistant
integrációja. A HA a helyi hálón magától megtalálja a naplózót, a
párosításhoz csak a naplózó jelszavát kéri, és utána:

- **Állapot:** nyugalom / csönget / beszélgetés, melyik lakás, mióta;
- **Esemény:** csöngetés, felvétel, a hívás vége, ajtónyitás, belépés kóddal
  vagy proxival stb., automatizáláshoz;
- **Gombok:** felvétel, letevés, ajtónyitás a vonalon lévő hívásban.

Hogy egy gomb végrehajtható-e, azt maga a naplózó dönti el: felvenni csak
csöngetéskor, letenni és ajtót nyitni csak felvett hívásban lehet, és csak az
engedélyezett lakásokban. A HA vagy a hálózat hibája így sem nyithat ajtót
máskor.

- **Kaputelefon panel** (oldalsáv): hallgatás és beszéd a hívóval, felvétel,
  letevés, ajtónyitás, a HA saját felületén, mobilról és a Nabu Casán át is.
  Megnyitáskor magától kapcsolódik; a hang az első koppintással indul
  (Felvétel, beszéd vagy „Hang bekapcsolása”), mert a böngésző csak így ad
  hangot és mikrofont. A hanghoz HTTPS kell: `http://` címen a gombok
  működnek, és a panel a HTTPS címre mutat. A `/kaputelefon?hivas=1` cím
  egy koppintással fel is veszi a csöngető hívást.

Készül még: az értesítés csöngetéskor automatizálás nélkül.

## Telepítés

1. HACS → a jobb felső ⋮ menü → **Egyéni tárolók** (Custom repositories) →
   tároló: `https://github.com/nonitex/codefon-ha`, típus: **Integráció**.
2. A HACS-ben keresd meg a **Codefon**-t → **Letöltés**, majd indítsd újra a
   Home Assistantot.
3. A naplózó magától megjelenik a **Beállítások → Eszközök és szolgáltatások**
   oldalon „Felfedezve” alatt. Ha nem, ugyanott: **Integráció hozzáadása →
   Codefon**, és add meg a címét.
4. Add meg a naplózó jelszavát. A HA csak a párosítást őrzi meg, a jelszót nem.
   A párosítás a naplózó Beállítások oldalán bármikor törölhető.

A naplózón legalább a protokoll 1. változatát tudó firmware kell (az
mDNS-ben `_codefon._tcp`, `proto=1`).

Home Assistant 2026.11-től a HACS helyett a beépített **Marketplace** van; az
egyéni tárolók oda átkerülnek, a telepítés ugyanígy megy.

## English

Home Assistant integration for the Codefon intercom logger: zeroconf
discovery, pairing with the logger's password, a state sensor, an event
entity and pick-up / hang-up / door buttons (the logger itself decides
whether a command is allowed in the call on the line). Install as a HACS
custom repository of type Integration.
