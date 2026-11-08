# Pokémon Fulldex for LiveContainer

In LiveContainer on your iPhone, open **Sources → +** and paste:

```text
https://raw.githubusercontent.com/spcrts1-arch/pokemon-fulldex-source/main/source.json
```

Then expand the source and tap **Install** next to Pokémon Fulldex. LiveContainer also accepts this URL to add the source:

```text
livecontainer://source?url=https%3A%2F%2Fraw.githubusercontent.com%2Fspcrts1-arch%2Fpokemon-fulldex-source%2Fmain%2Fsource.json
```

## Updates and saves

Use **Sources → Refresh** to load the current catalog, then tap **Install**. If LiveContainer asks how to install it, choose to replace your existing Pokémon Fulldex entry. LiveContainer keeps that entry's data containers when replacing it. Export a backup of important saves first. Saves from a separate, standalone installation can be exported there and imported in Fulldex inside LiveContainer.

Fulldex currently reuses the same iOS version and build numbers across releases. Use the upstream release date and tag in the source to tell builds apart.

## How the catalog stays current

[GitHub Actions](https://github.com/spcrts1-arch/pokemon-fulldex-source/actions/workflows/update-source.yml) checks [official stable releases](https://github.com/mamesj/pokemon-fulldex/releases) twice an hour and can also be run on demand. It verifies the official SHA-256, the IPA archive and the iOS bundle metadata before publishing a new download. The workflow also rechecks the current IPA at least once each calendar month and records the successful check in [status.json](status.json). A failed check leaves the published catalog in place.

This is a community catalog. The app download goes directly to the upstream release. The icon is extracted from that official IPA and belongs to the [Pokémon Fulldex project](https://github.com/mamesj/pokemon-fulldex); its upstream license is included in [UPSTREAM-LICENSE.txt](UPSTREAM-LICENSE.txt).
