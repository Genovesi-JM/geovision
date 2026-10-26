import 'dart:io';
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// The OS viewer/save sheet receives a temporary PDF, never an authenticated URL.
class ReportFiles {
  Future<Directory> _directory() async =>
      Directory('${(await getTemporaryDirectory()).path}/geovision_reports');

  Future<void> clear() async {
    final directory = await _directory();
    if (await directory.exists()) await directory.delete(recursive: true);
  }

  Future<void> present(Uint8List bytes,
      {required bool save, required Rect origin}) async {
    await presentFile(bytes,
        filename: 'GeoVision-report.pdf',
        mime: 'application/pdf',
        save: save,
        origin: origin);
  }

  Future<void> presentFile(Uint8List bytes,
      {required String filename,
      required String mime,
      required bool save,
      required Rect origin}) async {
    final root = await _directory();
    await root.create(recursive: true);
    final directory = await root.createTemp('report_');
    final safeName = filename.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
    final file = File('${directory.path}/$safeName');
    await file.writeAsBytes(bytes, flush: true);
    if (save) {
      await SharePlus.instance.share(ShareParams(
        files: [XFile(file.path, mimeType: mime)],
        sharePositionOrigin: origin,
      ));
    } else {
      final result = await OpenFilex.open(file.path, type: mime);
      if (result.type != ResultType.done) {
        throw StateError('PDF viewer unavailable');
      }
    }
  }
}

final reportFilesProvider = Provider<ReportFiles>((ref) => ReportFiles());
