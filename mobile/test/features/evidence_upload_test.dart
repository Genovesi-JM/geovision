import 'dart:convert';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/work/data/evidence_repository.dart';
import '../core/live_provider_selection_test.dart' show config;

class EvidenceAdapter implements HttpClientAdapter {
  EvidenceAdapter(this.file);
  final SelectedEvidence file;
  int uploads = 0;
  bool stored = false, loseResponse = false, forbidden = false, corrupt = false;
  final requests = <RequestOptions>[];
  Map<String, dynamic> get metadata => {
        'id': 'file-a',
        'dataset_id': 'dataset-a',
        'filename': file.filename,
        'size_bytes': file.bytes.length,
        'sha256_hash': file.hash,
        'mime_type': file.mime,
        'status': 'uploaded'
      };
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? stream,
      Future<void>? cancel) async {
    requests.add(options);
    Object data;
    if (forbidden) {
      return ResponseBody.fromString('{}', 403, headers: {
        'content-type': ['application/json']
      });
    }
    if (options.path.contains('/attachments/')) {
      return ResponseBody.fromBytes(corrupt ? [0] : file.bytes, 200);
    }
    if (options.path.endsWith('/upload')) {
      uploads++;
      expect(options.data, isA<FormData>());
      expect((options.data as FormData).files.single.value.filename,
          file.filename);
      stored = true;
      if (loseResponse) {
        loseResponse = false;
        throw DioException(
            requestOptions: options, type: DioExceptionType.connectionError);
      }
      data = {...metadata, if (corrupt) 'sha256_hash': 'wrong'};
    } else if (options.method == 'POST') {
      expect(options.data['asset_id'], 'asset-a');
      data = {'id': 'dataset-a'};
    } else {
      data = {
        'files': stored ? [metadata] : []
      };
    }
    return ResponseBody.fromString(jsonEncode(data), 200, headers: {
      'content-type': ['application/json']
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ApiClient api;
  late EvidenceAdapter adapter;
  late EvidenceRepository repo;
  late EvidenceDraft draft;
  late SelectedEvidence file;
  setUp(() async {
    FlutterSecureStorage.setMockInitialValues({});
    final tokens = SecureTokenStore();
    await tokens.saveTokens(access: 'test-access', refresh: 'test-refresh');
    file = SelectedEvidence(
        filename: 'survey.csv',
        bytes: Uint8List.fromList(utf8.encode('point,value\n1,2\n')));
    adapter = EvidenceAdapter(file);
    api = ApiClient(
        config: config(false),
        tokenStore: tokens,
        dio: Dio()..httpClientAdapter = adapter)
      ..selectWorkspace('workspace-a');
    repo = EvidenceRepository(api);
    draft = EvidenceDraft(assetId: 'asset-a', workspaceId: 'workspace-a')
      ..add(file);
  });
  Future<List<String>> upload() =>
      repo.upload(draft, cancel: CancelToken(), onProgress: (_) {});
  test('multipart evidence carries workspace/auth and downloads verified bytes',
      () async {
    expect(await upload(), ['dataset-file:file-a']);
    expect(adapter.uploads, 1);
    expect(await repo.download('request-a', file.uploaded!), file.bytes);
    for (final request in adapter.requests) {
      expect(request.headers['X-Workspace-ID'], 'workspace-a');
      expect(request.headers['Authorization'], 'Bearer test-access');
    }
    adapter.corrupt = true;
    await expectLater(repo.download('request-a', file.uploaded!),
        throwsA(isA<EvidenceFailure>()));
  });
  test('lost upload response reconciles by checksum without uploading twice',
      () async {
    adapter.loseResponse = true;
    await expectLater(upload(), throwsA(isA<DioException>()));
    expect(file.uploaded, isNull);
    expect(await upload(), ['dataset-file:file-a']);
    expect(adapter.uploads, 1);
  });
  test('forbidden and invalid receipts never produce attachment references',
      () async {
    adapter.forbidden = true;
    await expectLater(upload(), throwsA(isA<DioException>()));
    expect(file.uploaded, isNull);
    adapter.forbidden = false;
    adapter.corrupt = true;
    await expectLater(upload(), throwsA(isA<EvidenceFailure>()));
    expect(file.uploaded, isNull);
  });
  test('workspace changes and cancellation stop upload before network',
      () async {
    api.selectWorkspace('workspace-b');
    await expectLater(upload(), throwsA(isA<EvidenceFailure>()));
    api.selectWorkspace('workspace-a');
    await expectLater(
        repo.upload(draft, cancel: CancelToken()..cancel(), onProgress: (_) {}),
        throwsA(isA<EvidenceFailure>()));
    expect(adapter.requests, isEmpty);
  });
  test('limits and duplicates reject unusable selections', () {
    expect(() => draft.add(file), throwsA(isA<EvidenceFailure>()));
    expect(() => SelectedEvidence(filename: 'x.exe', bytes: Uint8List(1)),
        throwsA(isA<EvidenceFailure>()));
    expect(() => SelectedEvidence(filename: 'empty.pdf', bytes: Uint8List(0)),
        throwsA(isA<EvidenceFailure>()));
    expect(
        () => SelectedEvidence(
            filename: 'large.pdf', bytes: Uint8List(evidenceMaxBytes + 1)),
        throwsA(isA<EvidenceFailure>()));
  });
}
