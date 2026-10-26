import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart' as photos;

import '../../../app/providers.dart';
import '../domain/evidence.dart';
export '../domain/evidence.dart';
import '../../../core/networking/api_client.dart';

const evidenceMaxBytes = 10 * 1024 * 1024;
const evidenceTotalMaxBytes = 25 * 1024 * 1024;
const evidenceTypes = {
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'png': 'image/png',
  'pdf': 'application/pdf',
  'csv': 'text/csv'
};

class EvidenceFailure implements Exception {
  const EvidenceFailure(this.code);
  final String code;
}

class SelectedEvidence {
  SelectedEvidence({required this.filename, required this.bytes}) {
    final extension = filename.split('.').last.toLowerCase();
    if (!evidenceTypes.containsKey(extension)) {
      throw const EvidenceFailure('type');
    }
    if (bytes.isEmpty || bytes.length > evidenceMaxBytes) {
      throw const EvidenceFailure('size');
    }
    mime = evidenceTypes[extension]!;
    hash = sha256.convert(bytes).toString();
  }
  final String filename;
  final Uint8List bytes;
  late final String mime, hash;
  UploadedEvidence? uploaded;
}

class EvidencePicker {
  Future<SelectedEvidence?> pick({bool photo = false}) async {
    final XFile? file = photo
        ? await photos.ImagePicker()
            .pickImage(source: photos.ImageSource.gallery, imageQuality: 90)
        : await openFile(acceptedTypeGroups: const [
            XTypeGroup(label: 'Evidence', extensions: [
              'jpg',
              'jpeg',
              'png',
              'pdf',
              'csv'
            ], uniformTypeIdentifiers: [
              'public.jpeg',
              'public.png',
              'com.adobe.pdf',
              'public.comma-separated-values-text'
            ])
          ]);
    if (file == null) return null;
    if (await file.length() > evidenceMaxBytes) {
      throw const EvidenceFailure('size');
    }
    return SelectedEvidence(
        filename: file.name, bytes: await file.readAsBytes());
  }
}

class EvidenceDraft {
  EvidenceDraft({required this.assetId, required this.workspaceId});
  final String assetId, workspaceId;
  String? datasetId;
  final files = <SelectedEvidence>[];
  void add(SelectedEvidence file) {
    if (files.length >= 5) throw const EvidenceFailure('count');
    if (files.fold<int>(file.bytes.length, (sum, f) => sum + f.bytes.length) >
        evidenceTotalMaxBytes) {
      throw const EvidenceFailure('total');
    }
    if (files.any((f) => f.hash == file.hash)) {
      throw const EvidenceFailure('duplicate');
    }
    files.add(file);
  }
}

class EvidenceRepository {
  EvidenceRepository(this._api);
  final ApiClient _api;

  void _scope(EvidenceDraft draft, CancelToken cancel) {
    if (cancel.isCancelled) throw const EvidenceFailure('cancelled');
    if (_api.workspaceId != draft.workspaceId) {
      throw const EvidenceFailure('workspace');
    }
  }

  Future<List<String>> upload(EvidenceDraft draft,
      {required CancelToken cancel,
      required void Function(double) onProgress}) async {
    _scope(draft, cancel);
    final options = Options(
        headers: {'X-Workspace-ID': draft.workspaceId},
        receiveTimeout: const Duration(seconds: 90));
    if (draft.files.isEmpty) return [];
    if (draft.datasetId == null) {
      final response = await _api.raw.post('/datasets/',
          data: {
            'asset_id': draft.assetId,
            'name': 'Service request evidence',
            'dataset_type': 'SERVICE_EVIDENCE',
            'source_tool': 'manual',
            'metadata': {'purpose': 'service_request_evidence'},
          },
          options: options,
          cancelToken: cancel);
      draft.datasetId = '${response.data['id']}';
    }
    for (var index = 0; index < draft.files.length; index++) {
      _scope(draft, cancel);
      final file = draft.files[index];
      if (file.uploaded == null) {
        // Reconcile a previous timeout before uploading again. Only completed,
        // same-name, same-size, checksum-matching files in this draft are reused.
        final detail = await _api.raw.get('/datasets/${draft.datasetId}',
            options: options, cancelToken: cancel);
        for (final raw
            in (detail.data['files'] as List? ?? const []).whereType<Map>()) {
          if (raw['status'] == 'uploaded' &&
              raw['filename'] == file.filename &&
              raw['sha256_hash'] == file.hash &&
              raw['size_bytes'] == file.bytes.length) {
            file.uploaded = UploadedEvidence.fromJson(
                Map<String, dynamic>.from(raw),
                datasetId: draft.datasetId);
            break;
          }
        }
      }
      if (file.uploaded == null) {
        _scope(draft, cancel);
        final response = await _api.raw.post(
          '/datasets/${draft.datasetId}/upload',
          data: FormData.fromMap({
            'file': MultipartFile.fromBytes(file.bytes,
                filename: file.filename,
                contentType: DioMediaType.parse(file.mime))
          }),
          options: options,
          cancelToken: cancel,
          onSendProgress: (sent, total) {
            if (total > 0) {
              onProgress((index + sent / total) / draft.files.length);
            }
          },
        );
        final raw = Map<String, dynamic>.from(response.data as Map);
        if (raw['status'] != 'uploaded' ||
            raw['sha256_hash'] != file.hash ||
            raw['size_bytes'] != file.bytes.length) {
          throw const EvidenceFailure('integrity');
        }
        file.uploaded =
            UploadedEvidence.fromJson(raw, datasetId: draft.datasetId);
      }
      if (file.uploaded!.id.isEmpty) throw const EvidenceFailure('integrity');
      onProgress((index + 1) / draft.files.length);
    }
    _scope(draft, cancel);
    return draft.files.map((file) => file.uploaded!.reference).toList();
  }

  Future<Uint8List> download(String requestId, UploadedEvidence file) async {
    if (file.size <= 0 ||
        file.size > evidenceMaxBytes ||
        !evidenceTypes.values.contains(file.mime)) {
      throw const EvidenceFailure('type');
    }
    final workspace = _api.workspaceId;
    final result = await _api.raw.get<List<int>>(
        '/mobile/service-requests/${Uri.encodeComponent(requestId)}/attachments/${Uri.encodeComponent(file.id)}',
        options:
            Options(responseType: ResponseType.bytes, followRedirects: false));
    final bytes = Uint8List.fromList(result.data ?? const []);
    if (_api.workspaceId != workspace ||
        bytes.length != file.size ||
        sha256.convert(bytes).toString() != file.hash) {
      throw const EvidenceFailure('integrity');
    }
    return bytes;
  }
}

final evidencePickerProvider =
    Provider<EvidencePicker>((ref) => EvidencePicker());
final evidenceRepositoryProvider = Provider<EvidenceRepository>(
    (ref) => EvidenceRepository(ref.watch(apiClientProvider)));
