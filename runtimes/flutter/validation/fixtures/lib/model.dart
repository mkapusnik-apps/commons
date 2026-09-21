import 'package:json_annotation/json_annotation.dart';

part 'model.g.dart';

@JsonSerializable()
class Reading {
  final int value;
  const Reading(this.value);
  factory Reading.fromJson(Map<String, dynamic> json) => _$ReadingFromJson(json);
  Map<String, dynamic> toJson() => _$ReadingToJson(this);
}
