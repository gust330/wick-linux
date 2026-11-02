Name:           wick
Version:        0.1.0
Release:        1%{?dist}
Summary:        Close the lid. Keep working. Linux laptop lid-close sleep inhibitor

License:        MIT
URL:            https://github.com/gust330/wick-linux
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
Requires:       systemd
Requires:       python3

%description
Wick keeps your Linux laptop awake with the lid closed so coding agents, builds,
and downloads finish while you walk away. It manages systemd-logind inhibitor
locks safely without requiring root or sudo privileges.

%prep
%autosetup

%build
%py3_build

%install
%py3_install
install -D -m 0644 systemd/wick-guard.service %{buildroot}%{_userunitdir}/wick-guard.service

%files
%license LICENSE
%doc README.md
%{_bindir}/wick
%{python3_sitelib}/wick*
%{_userunitdir}/wick-guard.service

%changelog
* Sun Nov 01 2026 gust330 <gust330@users.noreply.github.com> - 0.1.0-1
- Initial Linux port for Fedora and systemd distributions
