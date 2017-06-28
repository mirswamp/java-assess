package org.continousassurance.swamp;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.maven.artifact.DependencyResolutionRequiredException;
import org.apache.maven.project.MavenProject;
import org.codehaus.plexus.util.FileUtils;
import org.continousassurance.swamp.AbstractSwampMojo;

/**
 * Goal which gets package info for swamp.
 *
 * @goal getTestCompile
 * @phase process-test-resources
 * @requiresDependencyResolution test
 * @Requiresdirectinvocation true
 * @requiresProject true
 */
public class TestCompileMojo extends AbstractSwampMojo {

	/**
	 * The file encoding to use when reading the source files. If the property <code>project.build.sourceEncoding</code>
	 * is not set, the platform default encoding is used.
	 *
	 * @parameter default-value="${maven.test.skip}"
	 * @readonly
	 */
	boolean skipTestCompile;

	/**
     * <p>
     * Specify where to place generated source files created by annotation processing.
     * Only applies to JDK 1.6+
     * </p>
     * 
     * @parameter( defaultValue = "${project.build.directory}/generated-test-sources/test-annotations" )
     * @readonly
	 */
    private File generatedTestSourcesDirectory;

    /**
     * @parameter expression="${swamp.build.monitor.output}" default-value="build_artifacts.xml"
     * @required
     * @readonly
     */
    private String buildMonitorOutputFile;

	/**
	 * @parameter default-value="${project}"
	 * @required
	 * @readonly
	 */
	MavenProject project;

	@Override
	protected MavenProject getProject() {
		return project;
	}
	
	@Override
	protected File getBuildMonitorOutputFile(){
		return new File(buildMonitorOutputFile);
	}
	
@Override
	protected boolean skipCompile() {
		boolean skip = false;
		if((getProject().getProperties().getProperty("maven.test.skip", "false").compareToIgnoreCase("true") == 0) ||
				(skipTestCompile == true)) {
			skip = true;
		}
		return skip;
	}

	@Override
	protected File getGeneratedSourcesDirectory() {
		return generatedTestSourcesDirectory;
	}

	@Override
	protected List<File> getSourceDirectories() {
		List<File> src_dirs = new ArrayList<File>();
		
		if(getProject().getTestCompileSourceRoots() != null) {
			
			for(String dirname : (List<String>)(List<?>)getProject().getTestCompileSourceRoots()){
				File dir = new File(dirname);
				try {
					if(dir.exists() && (!FileUtils.getFiles(dir, AbstractSwampMojo.ALL_JAVA_PATTERN, null).isEmpty())){
						src_dirs.add(dir);
					}
				} catch (IOException e) {
					// TODO Auto-generated catch block
					e.printStackTrace();
				}
			}
		}
		
		try {
			if (getGeneratedSourcesDirectory() != null && 
					getGeneratedSourcesDirectory().exists() && 
					!FileUtils.getFiles(getGeneratedSourcesDirectory(), AbstractSwampMojo.ALL_JAVA_PATTERN, null).isEmpty()){
				src_dirs.add(getGeneratedSourcesDirectory());
			}
		} catch (IOException e) {
			e.printStackTrace();
		}

		return src_dirs;
	}

	@Override
	protected List<String> getIncludeFileFilters() {
		return getFileFilters(getProject(), "testIncludes", AbstractSwampMojo.ALL_JAVA_PATTERN);
	}

	@Override
	protected List<String> getExcludeFileFilters() {
		return getFileFilters(getProject(), "testExcludes", "");
	}

	@Override
	protected File getOutputDirectory() {
		return new File(getProject().getBuild().getTestOutputDirectory());
	}

	@Override
	protected String getSourceVersion() {
		return getPluginParameter("org.apache.maven.plugins:maven-compiler-plugin",
				"testSource",
				"maven.compiler.testSource",
				"1.5");
	}

	@Override
	protected String getTargetVersion() {
		return getPluginParameter("org.apache.maven.plugins:maven-compiler-plugin",
				"testTarget",
				"maven.compiler.testTarget",
				"1.5");
	}

	@Override
	protected List<String> getClasspathFiles() throws DependencyResolutionRequiredException {
		// TODO Auto-generated method stub
		return getProject().getTestClasspathElements();
	}

}
