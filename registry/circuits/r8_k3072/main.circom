pragma circom 2.1.6;
include "../../qdot_rows.circom";
component main {public [q8, s1, s2]} = QDotRows(8, 3072);
