# Qubinaire CRM Flutter client

Shared Flutter source for Android and Windows. The client now has a local-first cache/outbox for all writable core CRM modules, plus a read-only employee directory cache.

## Offline coverage
- Leads: create/edit, initial bootstrap, queued retry, optimistic version checks and incremental pull.
- Activities, follow-ups, daily reports, courses, admissions, payments, targets, attendance, leave requests, refund requests, incentive payouts and incentive settings: local cache, JSON-based offline create/edit, durable outbox, automatic push/pull and server-side role/record checks.
- Employees/users: role-scoped read-only cache. Employee creation, role changes and password changes remain online/admin-only.
- Numeric-ID records created offline receive a server ID after sync; the client stores the local-to-server ID map and the server resolves dependent foreign keys in the same push batch.
- Optimistic conflict checks use a base snapshot. Rejected changes remain visible as conflicts and must be reviewed/re-entered.
- Sync is triggered every 30 seconds while the app is open, on connectivity restoration and on app resume. Offline login after a successful first login uses the stored device-bound session.

## Deliberate limitations / release gates
- Delete operations are disabled in the offline queue. Use status/archive fields where the module supports them.
- Attachments and binary documents are not synced.
- The general module editor currently accepts JSON fields; it is a functional pilot editor, not a polished field-by-field mobile form.
- Android background sync after the app is force-closed is not implemented; sync resumes when the app is opened.
- Local SQLite is not SQLCipher-encrypted. Use OS device encryption, MDM/remote wipe, TLS or private VPN, and dummy/pilot data until an encrypted local database and independent mobile security review are completed.
- Server sync uses PostgreSQL advisory transaction locking for ordered event commits, but live concurrency, database migration and multi-device conflict tests still need to run in staging.

## Generate native projects and build
Install Flutter stable SDK.
- Android: run `BUILD_ANDROID_APK.bat` on a machine with Android SDK and Java.
- Windows: run `BUILD_WINDOWS_EXE.bat` on Windows with Visual Studio Desktop development with C++ workload and Inno Setup 6.
- GitHub Actions: push the repository to GitHub and run `.github/workflows/build-clients.yml`; download the `qubinaire-android-apk` and `qubinaire-windows-installer` artifacts from the completed workflow.

The Android app needs a reachable office API URL, not `127.0.0.1` (that points to the phone itself). Do not use plain HTTP over an untrusted network. Configure a private VPN or TLS reverse proxy before connecting remote devices.

Actual compilation and device testing must be completed on SDK-enabled build machines before distributing the APK/installer.
