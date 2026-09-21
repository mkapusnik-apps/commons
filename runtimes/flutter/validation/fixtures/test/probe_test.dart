import 'package:flutter_test/flutter_test.dart';
import 'package:runtime_probe/main.dart';
import 'package:runtime_probe/model.dart';

void main() {
  test('generated JSON serializer round-trips the value', () {
    expect(Reading.fromJson(const Reading(42).toJson()).value, 42);
  });

  testWidgets('renders the probe reading', (tester) async {
    await tester.pumpWidget(const Probe());
    expect(find.text('Reading 42'), findsOneWidget);
  });
}
