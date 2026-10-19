# Desktop release signing

Public version-tagged releases must be signed before they can be published. The release workflow fails closed if signing credentials are missing, and verifies the resulting signatures before uploading the native installers. Pull request, branch, and local development builds do not need signing credentials.

## macOS: Developer ID and notarization

Gatekeeper accepts the distributed app when it has a valid Developer ID Application signature and an Apple notarization ticket. The macOS release build enables Hardened Runtime, signs the app, submits it to Apple's notarization service, and checks the signature, Gatekeeper assessment, and stapled ticket.

The repository owner must have an active Apple Developer Program membership and create:

- A Developer ID Application certificate exported as a password-protected `.p12` file. Base64-encode the file contents for the GitHub secret.
- An App Store Connect API key with the role required to submit software for notarization. Base64-encode the `.p8` file contents.
- The certificate password, API key ID, issuer ID, and Apple Developer team ID.

Add these GitHub repository Actions secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
| --- | --- |
| `MAC_CSC_LINK` | Base64-encoded Developer ID Application `.p12` |
| `MAC_CSC_KEY_PASSWORD` | Password used to export the `.p12` |
| `APPLE_API_KEY` | Base64-encoded App Store Connect `.p8` key |
| `APPLE_API_KEY_ID` | App Store Connect key ID |
| `APPLE_API_ISSUER` | App Store Connect issuer ID |
| `APPLE_TEAM_ID` | Apple Developer team ID |

Never commit certificate files, passwords, or private API keys. Once these secrets exist, a version tag will produce a signed, notarized DMG and ZIP. The current published v0.1.0 files were produced before this release gate and remain unsigned; they must be replaced by a new signed release after credentials are configured.

## Windows: Authenticode

The Windows release executable must have a valid Authenticode signature. This workflow currently uses an exportable PFX code-signing certificate from a trusted certificate authority. Add:

| Secret | Value |
| --- | --- |
| `WIN_CSC_LINK` | Base64-encoded, password-protected `.pfx` file |
| `WIN_CSC_KEY_PASSWORD` | Password used to export the `.pfx` |

electron-builder reads the PFX from an environment variable, so keep the base64 value below Windows' 8 KB environment-variable limit. If necessary, export only the signing certificate and private key without embedding the full intermediate certificate chain.

The release job checks the executable's Authenticode status before publication. Keep the same signing identity between releases so publisher reputation can accumulate. Microsoft SmartScreen may still display a warning for a new app or publisher until it has enough positive reputation; signing identifies the publisher but cannot guarantee that every first-time download will be warning-free. Microsoft's Store distribution is the reliable way to avoid SmartScreen download warnings entirely, and requires a separate Microsoft Partner Center submission.

## Linux and download integrity

Linux distributions do not share macOS Gatekeeper's notarization system. GitHub release assets are served over HTTPS, and the release includes a SHA-256 manifest so downloads can be checked for corruption. The manifest does not replace an independently trusted signature; users with stricter supply-chain requirements should build from source or verify future signed provenance attestations.
