# Fonts

The design system uses **Inter** (matching geovisionops.com). To bundle it:

1. Download Inter (OFL) from https://fonts.google.com/specimen/Inter
2. Drop `Inter-Regular.ttf`, `Inter-Medium.ttf`, `Inter-SemiBold.ttf`,
   `Inter-Bold.ttf`, `Inter-ExtraBold.ttf` into this folder.
3. Uncomment the `fonts:` section in `pubspec.yaml`.

Until then the app falls back to the platform sans-serif (no error).
