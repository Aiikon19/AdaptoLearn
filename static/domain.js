export function buildStudentEmail(local, institution) {
  return local.trim().toLowerCase() + '@' + institution.studentEmailDomain;
}
export function validLocalPart(local) {
  return /^[a-zA-Z0-9._%+-]+$/.test(local.trim());
}
export function changeDomain(local, institution) {
  return {
    local,
    suffix: '@' + institution.studentEmailDomain,
    example: 'Use your official student email, e.g. 221234567@' + institution.studentEmailDomain,
  };
}
