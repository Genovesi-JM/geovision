class UploadedEvidence {
  const UploadedEvidence(
      {required this.id,
      required this.datasetId,
      required this.filename,
      required this.size,
      required this.mime,
      required this.hash});
  final String id, datasetId, filename, mime, hash;
  final int size;
  String get reference => 'dataset-file:$id';
  factory UploadedEvidence.fromJson(Map<String, dynamic> json,
          {String? datasetId}) =>
      UploadedEvidence(
        id: '${json['id'] ?? ''}',
        datasetId: datasetId ?? '${json['dataset_id'] ?? ''}',
        filename: '${json['filename'] ?? ''}',
        size: (json['size_bytes'] as num?)?.toInt() ?? 0,
        mime: '${json['mime_type'] ?? ''}',
        hash: '${json['sha256_hash'] ?? ''}',
      );
  Map<String, dynamic> toJson() => {
        'id': id,
        'dataset_id': datasetId,
        'filename': filename,
        'size_bytes': size,
        'mime_type': mime,
        'sha256_hash': hash
      };
}
