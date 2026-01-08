import 'package:flutter/material.dart';

class SectorScreen extends StatelessWidget {
  const SectorScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final sectors = [
      'Infrastructure',
      'Construction',
      'Mining',
      'Demining',
      'Agriculture',
      'Livestock',
    ];

    return SafeArea(
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: sectors.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final sector = sectors[index];
          return Card(
            child: ListTile(
              title: Text(sector),
              subtitle: const Text('Tap to explore projects and KPIs'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () {},
            ),
          );
        },
      ),
    );
  }
}
