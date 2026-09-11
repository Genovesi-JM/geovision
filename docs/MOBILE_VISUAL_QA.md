# Mobile visual QA

GeoVision validates every mobile UI change against compact and standard iOS
and Android viewports before it is committed.

## Required device matrix

| Profile | Logical viewport | Purpose |
| --- | --- | --- |
| Compact iPhone | 320 × 568 | Smallest supported iOS layout |
| Standard iPhone | 393 × 852 | Current iPhone layout and safe areas |
| Compact Android | 360 × 640 | Small Android layout |
| Standard Android | 412 × 915 | Current Android layout |

The responsive widget test opens Inicio, Activos, Acciones, Servicios and Más
at every size and fails when Flutter reports a layout exception or the main
scaffold exceeds the viewport.

```sh
cd mobile
flutter test test/features/responsive_layout_test.dart
```

## Screenshot workflow

Before changing a mobile screen, preserve its current capture under
`artifacts/mobile-visual-audit/before`. After the change, regenerate the audit
set and inspect every affected screen at both widths.

```sh
cd mobile
GV_SCREENSHOT_DIR=../artifacts/mobile-visual-audit/after \
  flutter test test/visual_snapshot_test.dart
```

The screenshot test is skipped during ordinary test runs unless
`GV_SCREENSHOT_DIR` is supplied. This keeps CI fast while retaining a
repeatable, deterministic visual-review command. Important releases should
also be installed on at least one iOS Simulator and one Android Emulator so
system safe areas, status bars and navigation areas are included in the final
review.

## Acceptance checklist

- No horizontal clipping, overflow warning or unintended horizontal scroll.
- Text remains readable and may wrap or ellipsize without covering controls.
- Touch controls remain fully visible and comfortably tappable.
- Bottom navigation and floating actions respect system safe areas.
- Cards, grids and filters reflow instead of becoming narrower than their
  content.
- Screenshots are reviewed after the final code change, not only before it.
