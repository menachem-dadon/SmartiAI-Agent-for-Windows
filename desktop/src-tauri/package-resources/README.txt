Generated release staging directory.

scripts/build_tauri_release.ps1 places smarti-core/ and runtime/ here before
invoking the Tauri bundler. Those generated payloads are ignored by Git.
