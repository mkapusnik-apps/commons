import 'package:flutter/material.dart';
import 'model.dart';

void main() => runApp(const Probe());

class Probe extends StatelessWidget {
  const Probe({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    home: Scaffold(body: Text('Reading ${const Reading(42).value}')),
  );
}
